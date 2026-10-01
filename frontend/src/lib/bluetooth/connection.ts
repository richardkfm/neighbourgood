/**
 * Web Bluetooth connection manager for BitChat BLE gateway.
 *
 * Connects to a single nearby native BitChat node as a leaf node.
 * The native app handles mesh routing; we just read/write one GATT characteristic.
 */

import { get } from 'svelte/store';
import { t } from 'svelte-i18n';

// BitChat BLE protocol constants
const BITCHAT_SERVICE_UUID = '0000fff0-0000-1000-8000-00805f9b34fb';
const BITCHAT_CHARACTERISTIC_UUID = 'a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d';

export type ConnectionState = 'disconnected' | 'scanning' | 'connecting' | 'connected';

export type MessageCallback = (data: DataView) => void;

let device: BluetoothDevice | null = null;
let characteristic: BluetoothRemoteGATTCharacteristic | null = null;
let messageCallbacks: MessageCallback[] = [];
let disconnectCallback: (() => void) | null = null;

/** Check if Web Bluetooth is available in this browser. */
export function isBluetoothSupported(): boolean {
	return typeof navigator !== 'undefined' && 'bluetooth' in navigator;
}

/** Prompt user to select a nearby BitChat device. */
export async function scanForBitchatNode(): Promise<BluetoothDevice> {
	if (!isBluetoothSupported()) {
		throw new Error(get(t)('mesh.not_supported'));
	}
	const selected = await navigator.bluetooth.requestDevice({
		filters: [{ services: [BITCHAT_SERVICE_UUID] }],
		optionalServices: [BITCHAT_SERVICE_UUID]
	});
	return selected;
}

/** Connect to a selected BitChat device and subscribe to notifications. */
export async function connectToNode(
	selectedDevice: BluetoothDevice
): Promise<BluetoothRemoteGATTCharacteristic> {
	device = selectedDevice;

	// Listen for disconnection
	device.addEventListener('gattserverdisconnected', handleDisconnect);

	const server = await device.gatt!.connect();
	const service = await server.getPrimaryService(BITCHAT_SERVICE_UUID);
	characteristic = await service.getCharacteristic(BITCHAT_CHARACTERISTIC_UUID);

	// Subscribe to incoming messages via notifications
	await characteristic.startNotifications();
	characteristic.addEventListener('characteristicvaluechanged', handleNotification);

	return characteristic;
}

/** Disconnect from the current BitChat node. */
export function disconnect(): void {
	if (characteristic) {
		try {
			characteristic.removeEventListener('characteristicvaluechanged', handleNotification);
		} catch {
			// Ignore if already removed
		}
		characteristic = null;
	}
	if (device?.gatt?.connected) {
		device.gatt.disconnect();
	}
	device = null;
}

/**
 * Explicitly forget the device reference, preventing auto-reconnect.
 * Call this on manual disconnect.
 */
export function forgetDevice(): void {
	disconnect();
	device = null;
}

/** Check if there is a previously paired device that can be reconnected. */
export function hasLastDevice(): boolean {
	return device !== null && device.gatt !== undefined;
}

/**
 * Attempt to reconnect to the last paired device without a new user prompt.
 * Returns true on success, false on failure.
 */
export async function reconnectToLastDevice(): Promise<boolean> {
	if (!device || !device.gatt) return false;

	try {
		const server = await device.gatt.connect();
		const service = await server.getPrimaryService(BITCHAT_SERVICE_UUID);
		characteristic = await service.getCharacteristic(BITCHAT_CHARACTERISTIC_UUID);

		await characteristic.startNotifications();
		characteristic.addEventListener('characteristicvaluechanged', handleNotification);

		return true;
	} catch {
		characteristic = null;
		return false;
	}
}

/** Send raw bytes to the connected BitChat node. */
export async function sendMessage(data: Uint8Array): Promise<void> {
	if (!characteristic) {
		throw new Error(get(t)('mesh.not_connected'));
	}
	await characteristic.writeValueWithoutResponse(data);
}

/** Register a callback for incoming BLE messages. */
export function onMessage(callback: MessageCallback): () => void {
	messageCallbacks.push(callback);
	return () => {
		messageCallbacks = messageCallbacks.filter((cb) => cb !== callback);
	};
}

/** Register a callback for disconnection events. */
export function onDisconnect(callback: () => void): () => void {
	disconnectCallback = callback;
	return () => {
		if (disconnectCallback === callback) disconnectCallback = null;
	};
}

/** Get the connected device name, or null if not connected. */
export function getDeviceName(): string | null {
	return device?.name ?? null;
}

/** Check if currently connected to a GATT server. */
export function isConnected(): boolean {
	return device?.gatt?.connected === true && characteristic !== null;
}

// ── Internal handlers ───────────────────────────────────────────

function handleNotification(event: Event): void {
	const target = event.target as BluetoothRemoteGATTCharacteristic;
	if (target.value) {
		for (const cb of messageCallbacks) {
			try {
				cb(target.value);
			} catch {
				// Don't let one bad callback break the chain
			}
		}
	}
}

function handleDisconnect(): void {
	characteristic = null;
	if (disconnectCallback) {
		disconnectCallback();
	}
}
