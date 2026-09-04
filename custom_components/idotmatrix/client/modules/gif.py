from typing import Union, List
from ..connectionManager import ConnectionManager
import io
import logging
from PIL import Image as PilImage
import zlib


class Gif:
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.conn: ConnectionManager = ConnectionManager()

    def _load(self, file_path: str) -> bytes:
        """Load a gif file into a byte buffer.

        Args:
            file_path (str): path to file

        Returns:
            bytes: returns the file contents
        """
        with open(file_path, "rb") as file:
            return self._normalize_background(file.read())

    @staticmethod
    def _normalize_background(data: bytes) -> bytes:
        """Point the GIF's background color index at its darkest palette
        entry without re-encoding anything.

        The device appears to apply a new file's global palette (and its
        declared background) before the frame data has arrived, so a file
        whose index 0 is bright paints the panel white or in wrong colors
        for the length of the upload. Rendered GIFs already put black at
        index 0; this covers user-supplied files such as the photo folder.
        """
        try:
            if len(data) < 14 or data[:3] != b"GIF":
                return data
            packed = data[10]
            if not packed & 0x80:
                return data
            n = 2 << (packed & 7)
            gct = data[13:13 + n * 3]
            if len(gct) < n * 3:
                return data
            darkest = min(range(n), key=lambda i: gct[i * 3] + gct[i * 3 + 1] + gct[i * 3 + 2])
            if data[11] == darkest:
                return data
            out = bytearray(data)
            out[11] = darkest
            return bytes(out)
        except Exception:  # noqa: BLE001
            return data

    def _splitIntoChunks(self, data: bytearray, chunk_size: int) -> List[bytearray]:
        """Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def _createPayloads(
        self, gif_data: bytearray, chunk_size: int = 4096, index: int = 0x0d,
        interval: int = 5
    ) -> List[bytearray]:
        """Creates payloads from a GIF file.

        Args:
            gif_data (bytearray): data of the gif file
            chunk_size (int): size of a chunk
            index (int): GIF index byte. 0x0d (13) for single uploads,
                         0-11 for batch uploads.
            interval (int): Carousel interval in seconds (how long each GIF
                            displays before advancing). Range 0-255.

        Returns:
            List[bytearray]: returns list of bytearray payloads
        """
        # 16-byte chunk header
        header = bytearray(
            [
                255,  # [0:2] chunk_length (filled per chunk)
                255,
                1,    # [2] type: 1 = GIF
                0,    # [3] reserved
                0,    # [4] continuation: 0 = first, 2 = continuation
                255,  # [5:9] file_size (filled below)
                255,
                255,
                255,
                255,  # [9:13] CRC32 (filled below)
                255,
                255,
                255,
                interval & 0xFF,  # [13] carousel interval in seconds
                0,    # [14] reserved
                index & 0xFF,  # [15] index: 0x0d for single, GIF index for batch
            ]
        )
        # split gif into chunks
        chunks = []
        gif_chunks = self._splitIntoChunks(gif_data, chunk_size)
        # set gif length
        header[5:9] = int(len(gif_data)).to_bytes(4, byteorder="little")
        # set crc of gif
        crc = zlib.crc32(gif_data)
        header[9:13] = crc.to_bytes(4, byteorder="little")
        # iterate over chunks
        for i, chunk in enumerate(gif_chunks):
            # starting from the second chunk, set the header to 2
            header[4] = 2 if i > 0 else 0
            # set chunk length in header
            chunk_len = len(chunk) + len(header)
            header[0:2] = chunk_len.to_bytes(2, byteorder="little")
            # append chunk to chunk list
            chunks.append(bytearray(header) + chunk)
        return chunks

    async def uploadUnprocessed(self, file_path: str) -> Union[bool, bytearray]:
        """uploads an image without further checks and resizes.

        Args:
            file_path (str): path to the image file

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
        """
        try:
            gif_data = self._load(file_path)
            data = self._createPayloads(gif_data)
            if self.conn:
                await self.conn.connect()
                for chunk in data:
                    await self.conn.send(data=chunk)
            return data
        except BaseException as error:
            self.logging.error(f"could not upload gif unprocessed: {error}")
            return False

    def _processGif(self, file_path: str, pixel_size: int = 32, index: int = 0x0d,
                    interval: int = 5) -> Union[bool, List[bytearray]]:
        """Process a GIF file and create payloads (sync, for use in executor).

        Args:
            file_path (str): path to the image file
            pixel_size (int, optional): amount of pixels. Defaults to 32.
            index (int): GIF index byte for header[15].
            interval (int): Carousel interval in seconds.

        Returns:
            Union[bool, List[bytearray]]: False if error, otherwise list of payload chunks
        """
        try:
            with PilImage.open(file_path) as img:
                frames_rgb = []
                duration = img.info.get("duration", 100)
                try:
                    while True:
                        frame = img.copy().convert("RGB")
                        if frame.size != (pixel_size, pixel_size):
                            frame = frame.resize(
                                (pixel_size, pixel_size), PilImage.NEAREST
                            )
                        frames_rgb.append(frame)
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass

                # Quantize all frames to a single shared palette (no LCTs).
                # The device parser only supports a Global Color Table.
                palette_img = frames_rgb[0].quantize(colors=256)
                frames_p = []
                for rgb_frame in frames_rgb:
                    frames_p.append(rgb_frame.quantize(palette=palette_img))

                gif_buffer = io.BytesIO()
                frames_p[0].save(
                    gif_buffer,
                    format="GIF",
                    save_all=True,
                    append_images=frames_p[1:],
                    loop=0,
                    duration=duration,
                    disposal=2,
                )
                gif_buffer.seek(0)
                return self._createPayloads(gif_buffer.getvalue(), index=index, interval=interval)
        except BaseException as error:
            self.logging.error(f"could not process gif: {error}")
            return False

    async def uploadProcessed(
        self, file_path: str, pixel_size: int = 32, index: int = 0x0d,
        interval: int = 5
    ) -> Union[bool, bytearray]:
        """uploads a file processed to make sure everything is correct before uploading to the device.

        Args:
            file_path (str): path to the image file
            pixel_size (int, optional): amount of pixels (either 16 or 32 makes sense). Defaults to 32.
            index (int): GIF index byte. 0x0d for single, 0-11 for batch.
            interval (int): Carousel interval in seconds.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._processGif, file_path, pixel_size, index, interval)

            if data is False:
                return False

            if self.conn:
                await self.conn.connect()
                for chunk in data:
                    result = await self.conn.send(data=chunk, response=True)
                    if not result:
                        self.logging.error("Send failed during GIF upload")
                        return False
                self.logging.debug(f"GIF upload complete: {len(data)} chunks sent")
            return data
        except BaseException as error:
            self.logging.error(f"could not upload gif processed: {error}")
            return False

    async def uploadSingleRaw(self, file_path: str) -> bool:
        """Upload a single raw GIF using the single upload protocol (no batch commands).

        Uses index=0x0d which tells the device this is a standalone GIF, giving
        it access to the full GIF buffer (not the smaller per-slot batch buffer).

        Args:
            file_path: Path to the GIF file.

        Returns:
            True if successful, False on error.
        """
        import asyncio

        try:
            if not self.conn:
                return False

            await self.conn.connect()

            loop = asyncio.get_event_loop()
            gif_data = await loop.run_in_executor(None, self._load, file_path)
            data = self._createPayloads(gif_data, index=0x0d)

            for chunk in data:
                # Use response=True for flow control through BLE proxy.
                # Without it, the proxy's BLE transmit buffer overflows for
                # large files and silently drops packets.  Slower but reliable.
                result = await self.conn.send(data=chunk, response=True)
                if not result:
                    self.logging.error("Send failed during single GIF upload")
                    return False

            self.logging.debug(f"Single GIF upload complete: {len(data)} chunks, {len(gif_data)} bytes")
            return True

        except BaseException as error:
            self.logging.error(f"Single GIF upload failed: {error}")
            return False

    async def uploadBatch(
        self, file_paths: List[str], pixel_size: int = 32, interval: int = 5,
        raw: bool = False
    ) -> bool:
        """Upload multiple GIFs as a batch using the device's batch protocol.

        Sends up to 12 GIFs at once. The device will loop through them automatically.

        Args:
            file_paths: List of paths to GIF files (max 12).
            pixel_size: Pixel size for resizing (16 or 32). Defaults to 32.
            interval: Carousel interval in seconds (how long each GIF displays
                      before advancing to the next). Range 0-255. Defaults to 5.
            raw: If True, send raw file bytes without Pillow re-encoding.

        Returns:
            True if successful, False on error.
        """
        import asyncio

        if not file_paths:
            return False

        # Device supports max 12 GIFs per batch
        file_paths = file_paths[:12]
        count = len(file_paths)

        try:
            if not self.conn:
                return False

            await self.conn.connect()

            # 1. Send batch mode enable: 04 00 0a 01
            batch_enable = bytearray([0x04, 0x00, 0x0a, 0x01])
            await self.conn.send(data=batch_enable)
            # Brief pause for device to process command
            await asyncio.sleep(0.1)

            # 2. Send batch header with count and indices
            # Format: [length, 0x00, 0x02, 0x01, count, idx0, idx1, ...]
            batch_header = bytearray([0x00, 0x00, 0x02, 0x01, count])
            batch_header.extend(range(count))
            batch_header[0] = len(batch_header) & 0xFF
            batch_header[1] = (len(batch_header) >> 8) & 0xFF
            await self.conn.send(data=batch_header)
            await asyncio.sleep(0.1)

            # 3. Process and stream all GIFs with BLE-paced writes
            loop = asyncio.get_event_loop()
            for i, file_path in enumerate(file_paths):
                if raw:
                    # Send raw file bytes without Pillow re-encoding
                    gif_data = await loop.run_in_executor(None, self._load, file_path)
                    data = self._createPayloads(gif_data, index=i, interval=interval)
                else:
                    data = await loop.run_in_executor(
                        None, self._processGif, file_path, pixel_size, i, interval
                    )
                if data is False:
                    self.logging.error(f"Failed to process GIF {i}: {file_path}")
                    return False

                for chunk in data:
                    result = await self.conn.send(data=chunk, response=True)
                    if not result:
                        self.logging.error(f"Send failed at GIF {i}")
                        return False

                self.logging.debug(f"GIF {i+1}/{count} uploaded ({len(data)} chunks, {'raw' if raw else 'processed'})")
                # Brief pause between GIF files (~100-150ms seen in Android capture)
                if i < count - 1:
                    await asyncio.sleep(0.15)

            self.logging.debug(f"Batch upload complete: {count} GIFs, interval={interval}s")
            return True

        except BaseException as error:
            self.logging.error(f"Batch upload failed: {error}")
            return False
