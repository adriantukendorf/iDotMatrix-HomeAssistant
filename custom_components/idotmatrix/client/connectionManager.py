import asyncio
from bleak import BleakClient, BleakScanner, AdvertisementData
from .const import UUID_READ_DATA, UUID_WRITE_DATA, BLUETOOTH_DEVICE_NAME
import logging
import time
from typing import List, Optional


class SingletonMeta(type):
    logging = logging.getLogger(__name__)
    _instances: dict = {}

    def __call__(cls, *args, **kwargs) -> "SingletonMeta":
        if cls not in cls._instances:
            try:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            except:
                # return None if wrong (or no arguments are given)
                cls._instances[cls] = None
        return cls._instances[cls]


class ConnectionManager(metaclass=SingletonMeta):
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.address: Optional[str] = None
        self.client: Optional[BleakClient] = None
        self.hass = None

    def set_hass(self, hass):
        """Set Home Assistant instance for proxy support."""
        self.hass = hass

    @staticmethod
    async def scan() -> List[tuple[str, str]]:
        # This basic scan might not find proxy devices if not integrated with HA scanning
        # But we primarily rely on HA config flow now.
        logging.info("scanning for iDotMatrix bluetooth devices...")
        devices = await BleakScanner.discover(return_adv=True)
        filtered_devices: List[tuple[str, str]] = []
        for key, (device, adv) in devices.items():
            if (
                isinstance(adv, AdvertisementData)
                and adv.local_name
                and str(adv.local_name).startswith(BLUETOOTH_DEVICE_NAME)
            ):
                logging.info(f"found device {key} with name {adv.local_name}")
                filtered_devices.append((device.address, adv.local_name))
        return filtered_devices

    async def connectByAddress(self, address: str) -> None:
        self.address = address
        await self.connect()

    async def connectBySearch(self) -> None:
        devices = await self.scan()
        if devices:
            # connect to first device
            self.address = devices[0]
            await self.connect()
        else:
            self.logging.error("no target devices found.")

    async def connect(self) -> None:
        if self.address:
            # Check if client exists and is connected
            if self.client and self.client.is_connected:
                return

            try:
                device = None
                from bleak_retry_connector import establish_connection
                
                # Try to get device from HA Bluetooth coordinator
                if self.hass:
                    from homeassistant.components import bluetooth
                    
                    # Poll for device in HA cache (wait up to 15s)
                    # This allows time for Proxies to forward advertisements or local adapter to scan
                    for i in range(15):
                        device = bluetooth.async_ble_device_from_address(
                            self.hass, self.address, connectable=True
                        )
                        if device:
                            break
                        # Only sleep if we haven't found it yet
                        if i < 14:
                             await asyncio.sleep(1.0)
                
                # If we have a device object, use establish_connection
                if device:
                    self.logging.info(f"Connecting to {device.name} ({device.address})")
                    self.client = await establish_connection(
                        BleakClient, 
                        device, 
                        self.address,
                        max_attempts=3
                    )
                else:
                    # If device is not found in HA cache after polling, we cannot connect reliably.
                    # Fallback to direct client is unsafe in HA environment and usually fails with "No backend".
                    self.logging.error(f"Device {self.address} unavailable in Home Assistant Bluetooth mesh. Ensure it is powered and within range of an adapter or proxy.")
                    self.client = None
                    return
                    
                self.logging.info(f"connected to {self.address}")
            except Exception as e:
                self.logging.error(f"Failed to connect to {self.address}: {e}")
                # Clean up client on failure
                self.client = None
        else:
            self.logging.error("device address is not set.")

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            self.logging.info(f"disconnected from {self.address}")

    # Match the Android app's BLE write size (MTU 517 - ATT overhead = 509)
    BLE_WRITE_SIZE = 509

    # Default to acknowledged writes: through an ESPHome BLE proxy,
    # unacknowledged Write Commands are silently dropped under buffer
    # pressure (observed as e.g. Clock.setMode losing a style change and
    # the panel staying on the previous face).
    async def send(self, data, response=True):
        if self.client and self.client.is_connected:
            self.logging.debug("sending %d bytes to device", len(data))
            # Cap chunk size to real BLE MTU regardless of proxy-reported size.
            # ESPHome BLE proxies report a large WiFi-based MTU, but the actual
            # BLE radio to the device uses ~509-byte packets at ~25ms intervals.
            reported = self.client.services.get_characteristic(UUID_WRITE_DATA).max_write_without_response_size
            chunk_size = min(reported, self.BLE_WRITE_SIZE)
            for i in range(0, len(data), chunk_size):
                await self.client.write_gatt_char(UUID_WRITE_DATA, data[i:i+chunk_size], response=response)
                # Pace writes to match the BLE connection interval (~25ms).
                # The Android app's BLE stack provides this pacing via L2CAP
                # flow control; through an ESPHome proxy we must add it manually
                # to prevent flooding the proxy's BLE transmit buffer.
                await asyncio.sleep(0.025)

            return True

    async def read(self) -> bytes:
        if self.client and self.client.is_connected:
            data = await self.client.read_gatt_char(UUID_READ_DATA)
            self.logging.info("data received")
            return data
