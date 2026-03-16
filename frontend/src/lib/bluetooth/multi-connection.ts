/**
 * Multi-device BLE connection manager.
 *
 * Maintains connections to multiple BitChat gateway nodes simultaneously
 * for redundancy. Messages are broadcast to all connected devices.
 * Deduplication of incoming messages is handled by the mesh store's seenIds.
 */

import {
	isBluetoothSupported,
	scanForBitchatNode,
	type MessageCallback
} from './connection';

const BITCHAT_SERVICE_UUID = '0000fff0-0000-1000-8000-00805f9b34fb';
const BITCHAT_CHARACTERISTIC_UUID = 'a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d';

const MAX_DEVICES = 3;

export interface ConnectedDevice {
	id: string;
	name: string | null;
	device: BluetoothDevice;
	characteristic: BluetoothRemoteGATTCharacteristic;
	connectedAt: number;
}

let devices: Map<string, ConnectedDevice> = new Map();
let messageCallbacks: MessageCallback[] = [];
let disconnectCallbacks: ((deviceId: string) => void)[] = [];

/** Check if we can add more devices. */
export function canAddDevice(): boolean {
	return isBluetoothSupported() && devices.size < MAX_DEVICES;
}

/** Get all currently connected devices. */
export function getConnectedDevices(): ConnectedDevice[] {
	return Array.from(devices.values());
}

/** Get the number of connected devices. */
export function getDeviceCount(): number {
	return devices.size;
}

/** Connect to a new BitChat device. Prompts user with device picker. */
export async function addDevice(): Promise<ConnectedDevice> {
	if (devices.size >= MAX_DEVICES) {
		throw new Error(`Maximum ${MAX_DEVICES} devices reached`);
	}

	const bleDevice = await scanForBitchatNode();
	const deviceId = bleDevice.id || bleDevice.name || `device-${Date.now()}`;

	// Already connected?
	if (devices.has(deviceId)) {
		throw new Error('Already connected to this device');
	}

	bleDevice.addEventListener('gattserverdisconnected', () => {
		handleDeviceDisconnect(deviceId);
	});

	const server = await bleDevice.gatt!.connect();
	const service = await server.getPrimaryService(BITCHAT_SERVICE_UUID);
	const characteristic = await service.getCharacteristic(BITCHAT_CHARACTERISTIC_UUID);

	await characteristic.startNotifications();
	characteristic.addEventListener('characteristicvaluechanged', (event: Event) => {
		const target = event.target as BluetoothRemoteGATTCharacteristic;
		if (target.value) {
			for (const cb of messageCallbacks) {
				try { cb(target.value); } catch { /* skip */ }
			}
		}
	});

	const entry: ConnectedDevice = {
		id: deviceId,
		name: bleDevice.name ?? null,
		device: bleDevice,
		characteristic,
		connectedAt: Date.now(),
	};
	devices.set(deviceId, entry);

	return entry;
}

/** Disconnect a specific device. */
export function removeDevice(deviceId: string): void {
	const entry = devices.get(deviceId);
	if (!entry) return;

	try {
		entry.characteristic.removeEventListener('characteristicvaluechanged', () => {});
	} catch { /* ignore */ }

	if (entry.device.gatt?.connected) {
		entry.device.gatt.disconnect();
	}
	devices.delete(deviceId);
}

/** Disconnect all devices. */
export function removeAllDevices(): void {
	for (const [id] of devices) {
		removeDevice(id);
	}
}

/** Broadcast data to all connected devices. */
export async function broadcastToAll(data: Uint8Array): Promise<{ sent: number; failed: number }> {
	let sent = 0;
	let failed = 0;

	for (const [, entry] of devices) {
		try {
			await entry.characteristic.writeValueWithoutResponse(data);
			sent++;
		} catch {
			failed++;
		}
	}

	return { sent, failed };
}

/** Register a callback for incoming messages from any device. */
export function onMultiMessage(callback: MessageCallback): () => void {
	messageCallbacks.push(callback);
	return () => {
		messageCallbacks = messageCallbacks.filter((cb) => cb !== callback);
	};
}

/** Register a callback for device disconnection. */
export function onDeviceDisconnect(callback: (deviceId: string) => void): () => void {
	disconnectCallbacks.push(callback);
	return () => {
		disconnectCallbacks = disconnectCallbacks.filter((cb) => cb !== callback);
	};
}

function handleDeviceDisconnect(deviceId: string): void {
	devices.delete(deviceId);
	for (const cb of disconnectCallbacks) {
		try { cb(deviceId); } catch { /* skip */ }
	}
}
