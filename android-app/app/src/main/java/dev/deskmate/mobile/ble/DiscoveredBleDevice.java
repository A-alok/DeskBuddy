package dev.deskmate.mobile.ble;

import android.bluetooth.BluetoothDevice;

public class DiscoveredBleDevice {
    private final BluetoothDevice device;
    private int rssi;
    private final String name;

    public DiscoveredBleDevice(BluetoothDevice device, int rssi, String name) {
        this.device = device;
        this.rssi = rssi;
        this.name = (name != null && !name.trim().isEmpty()) ? name : "DeskMate";
    }

    public BluetoothDevice getDevice() {
        return device;
    }

    public int getRssi() {
        return rssi;
    }

    public void setRssi(int rssi) {
        this.rssi = rssi;
    }

    public String getName() {
        return name;
    }

    public String getAddress() {
        return device != null ? device.getAddress() : "00:00:00:00:00:00";
    }
}
