from typing import Union, List
from ..connectionManager import ConnectionManager
import io
import logging
from PIL import Image as PilImage
import zlib


class Image:
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.conn: ConnectionManager = ConnectionManager()

    async def setMode(self, mode: int = 1) -> Union[bool, bytearray]:
        """Enter the DIY draw mode of the iDotMatrix device.

        Args:
            mode (int): 0 = disable DIY, 1 = enable DIY. Defaults to 1.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise byte array of the command.
        """
        try:
            data = bytearray([5, 0, 4, 1, mode % 256])
            if self.conn:
                await self.conn.connect()
                await self.conn.send(data=data)
            return data
        except BaseException as error:
            self.logging.error(f"could not enter image mode due to {error}")
            return False

    def _splitIntoChunks(self, data: bytearray, chunk_size: int) -> List[bytearray]:
        """Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def _createPayloads(self, image_data: bytearray, chunk_size: int = 4096) -> List[bytearray]:
        """Creates payloads from image data using the 16-byte chunk header.

        Uses the same header format as GIF uploads, with type=2 for static images.

        Args:
            image_data (bytearray): raw RGB pixel data
            chunk_size (int): size of a data chunk

        Returns:
            List[bytearray]: list of bytearray payloads
        """
        # 16-byte chunk header (same format as GIF, type=2 for static image)
        header = bytearray(
            [
                255,  # [0:2] chunk_length (filled per chunk)
                255,
                2,    # [2] type: 2 = Static Image
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
                5,    # [13] carousel interval in seconds (default 5)
                0,    # [14] reserved
                0x0d, # [15] single upload marker
            ]
        )
        chunks = []
        data_chunks = self._splitIntoChunks(image_data, chunk_size)
        # set file length
        header[5:9] = int(len(image_data)).to_bytes(4, byteorder="little")
        # set CRC32
        crc = zlib.crc32(image_data)
        header[9:13] = crc.to_bytes(4, byteorder="little")
        # iterate over chunks
        for i, chunk in enumerate(data_chunks):
            header[4] = 2 if i > 0 else 0
            chunk_len = len(chunk) + len(header)
            header[0:2] = chunk_len.to_bytes(2, byteorder="little")
            chunks.append(bytearray(header) + chunk)
        return chunks

    async def uploadUnprocessed(self, file_path: str) -> Union[bool, bytearray]:
        """Uploads an image without further checks and resizes.

        Args:
            file_path (str): path to the image file

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
        """
        try:
            import asyncio

            def load_raw_rgb(path):
                with PilImage.open(path) as img:
                    img = img.convert("RGB")
                    return bytearray(img.tobytes())

            raw_data = await asyncio.to_thread(load_raw_rgb, file_path)
            data = self._createPayloads(raw_data)
            if self.conn:
                await self.conn.connect()
                for chunk in data:
                    await self.conn.send(data=chunk)
            return data
        except BaseException as error:
            self.logging.error(f"could not upload the unprocessed image: {error}")
            return False

    async def uploadProcessed(
        self, file_path: str, pixel_size: int = 32
    ) -> Union[bool, bytearray]:
        """Uploads a file processed and makes sure everything is correct before uploading to the device.

        Args:
            file_path (str): path to the image file
            pixel_size (int, optional): amount of pixels (either 16 or 32 makes sense). Defaults to 32.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
        """
        try:
            import asyncio

            def process_image_sync():
                with PilImage.open(file_path) as img:
                    img = img.convert("RGB")
                    if img.size != (pixel_size, pixel_size):
                        img = img.resize(
                            (pixel_size, pixel_size), PilImage.LANCZOS
                        )
                    # Return raw RGB pixel data (W*H*3 bytes)
                    return bytearray(img.tobytes())

            raw_data = await asyncio.to_thread(process_image_sync)
            data = self._createPayloads(raw_data)

            if self.conn:
                await self.conn.connect()
                for chunk in data:
                    await self.conn.send(data=chunk)
            return data
        except BaseException as error:
            self.logging.error(f"could not upload processed image: {error}")
            return False
