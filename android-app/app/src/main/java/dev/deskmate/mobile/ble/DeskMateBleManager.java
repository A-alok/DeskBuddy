package dev.deskmate.mobile.ble;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@SuppressLint("MissingPermission")
public class DeskMateBleManager {
    private static final String TAG = "DeskMateBLE";

    public static final UUID SERVICE_UUID = UUID.fromString("4fafc201-1fb5-459e-8fcc-c5c9c331914b");
    public static final UUID CHAR_SSID_UUID = UUID.fromString("beb5483e-36e1-4688-b7f5-ea07361b26a8");
    public static final UUID CHAR_PASS_UUID = UUID.fromString("beb5483e-36e1-4688-b7f5-ea07361b26a9");
    public static final UUID CHAR_STATUS_UUID = UUID.fromString("beb5483e-36e1-4688-b7f5-ea07361b26aa");
    public static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    public interface BleListener {
        void onDeviceDiscovered(DiscoveredBleDevice device);
        void onConnectionStateChange(boolean connected, String deviceName);
        void onStatusReceived(String status);
        void onProvisionSuccess(String assignedIp);
        void onError(String message);
    }

    private final Context context;
    private final Handler mainHandler;
    private BleListener listener;

    private BluetoothAdapter bluetoothAdapter;
    private BluetoothLeScanner bleScanner;
    private BluetoothGatt bluetoothGatt;
    private boolean isScanning = false;

    private String pendingSsid = null;
    private String pendingPass = null;

    public DeskMateBleManager(Context context) {
        this.context = context.getApplicationContext();
        this.mainHandler = new Handler(Looper.getMainLooper());

        BluetoothManager bluetoothManager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        if (bluetoothManager != null) {
            this.bluetoothAdapter = bluetoothManager.getAdapter();
            if (this.bluetoothAdapter != null) {
                this.bleScanner = this.bluetoothAdapter.getBluetoothLeScanner();
            }
        }
    }

    public void setListener(BleListener listener) {
        this.listener = listener;
    }

    public boolean isBluetoothEnabled() {
        return bluetoothAdapter != null && bluetoothAdapter.isEnabled();
    }

    public boolean isScanning() {
        return isScanning;
    }

    public void startScan() {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled()) {
            notifyError("Bluetooth is disabled on this phone.");
            return;
        }

        if (bleScanner == null) {
            bleScanner = bluetoothAdapter.getBluetoothLeScanner();
        }

        if (bleScanner == null) {
            notifyError("Unable to obtain Bluetooth LE scanner.");
            return;
        }

        if (isScanning) return;

        isScanning = true;
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build();

        List<ScanFilter> filters = new ArrayList<>();
        // Optional filter, or scan all and filter by DeskMate prefix
        try {
            bleScanner.startScan(filters, settings, scanCallback);
            mainHandler.postDelayed(() -> {
                if (isScanning) {
                    stopScan();
                }
            }, 12000);
        } catch (Exception e) {
            isScanning = false;
            notifyError("Scan start failed: " + e.getMessage());
        }
    }

    public void stopScan() {
        if (!isScanning) return;
        isScanning = false;
        try {
            if (bleScanner != null) {
                bleScanner.stopScan(scanCallback);
            }
        } catch (Exception ignored) {}
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            if (device == null) return;

            String name = device.getName();
            if (name == null && result.getScanRecord() != null) {
                name = result.getScanRecord().getDeviceName();
            }

            // Look for DeskMate or dev boards
            if (name != null && (name.contains("DeskMate") || name.contains("ESP32") || name.contains("DeskBuddy"))) {
                DiscoveredBleDevice discovered = new DiscoveredBleDevice(device, result.getRssi(), name);
                mainHandler.post(() -> {
                    if (listener != null) {
                        listener.onDeviceDiscovered(discovered);
                    }
                });
            }
        }

        @Override
        public void onScanFailed(int errorCode) {
            isScanning = false;
            notifyError("Scan failed with error code: " + errorCode);
        }
    };

    public void connect(BluetoothDevice device) {
        stopScan();
        disconnect();

        try {
            bluetoothGatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
        } catch (Exception e) {
            notifyError("Connect failed: " + e.getMessage());
        }
    }

    public void disconnect() {
        if (bluetoothGatt != null) {
            try {
                bluetoothGatt.disconnect();
                bluetoothGatt.close();
            } catch (Exception ignored) {}
            bluetoothGatt = null;
        }
        mainHandler.post(() -> {
            if (listener != null) {
                listener.onConnectionStateChange(false, null);
            }
        });
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                Log.d(TAG, "Connected to GATT server, discovering services...");
                gatt.discoverServices();
                mainHandler.post(() -> {
                    if (listener != null) {
                        String name = gatt.getDevice().getName();
                        listener.onConnectionStateChange(true, name != null ? name : "DeskMate");
                    }
                });
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                Log.d(TAG, "Disconnected from GATT server");
                disconnect();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                BluetoothGattService service = gatt.getService(SERVICE_UUID);
                if (service != null) {
                    BluetoothGattCharacteristic statusChar = service.getCharacteristic(CHAR_STATUS_UUID);
                    if (statusChar != null) {
                        // Subscribe to status notifications
                        gatt.setCharacteristicNotification(statusChar, true);
                        BluetoothGattDescriptor descriptor = statusChar.getDescriptor(CCCD_UUID);
                        if (descriptor != null) {
                            descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                            gatt.writeDescriptor(descriptor);
                        }
                    }
                }
                notifyStatus("Ready for Wi-Fi credentials");
            } else {
                notifyError("Service discovery failed with status: " + status);
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            handleStatusUpdate(characteristic.getValue());
        }

        @Deprecated
        @Override
        public void onCharacteristicRead(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                handleStatusUpdate(characteristic.getValue());
            }
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) {
                if (characteristic.getUuid().equals(CHAR_SSID_UUID) && pendingPass != null) {
                    // After SSID written, write password
                    mainHandler.postDelayed(() -> writePasswordInternal(pendingPass), 150);
                } else if (characteristic.getUuid().equals(CHAR_PASS_UUID)) {
                    notifyStatus("Credentials sent. DeskMate connecting to Wi-Fi...");
                }
            } else {
                notifyError("Write failed with status: " + status);
            }
        }
    };

    private void handleStatusUpdate(byte[] data) {
        if (data == null) return;
        String raw = new String(data, StandardCharsets.UTF_8).trim();
        Log.d(TAG, "Received BLE status: " + raw);

        mainHandler.post(() -> {
            if (listener != null) {
                listener.onStatusReceived(raw);
                if (raw.startsWith("CONNECTED:") || raw.startsWith("CONNECTED ")) {
                    String ip = raw.replace("CONNECTED:", "").replace("CONNECTED", "").trim();
                    listener.onProvisionSuccess(ip);
                }
            }
        });
    }

    public void provisionWifi(String ssid, String password) {
        if (bluetoothGatt == null) {
            notifyError("Not connected to DeskMate over Bluetooth.");
            return;
        }

        BluetoothGattService service = bluetoothGatt.getService(SERVICE_UUID);
        if (service == null) {
            notifyError("DeskMate provisioning service not found on device.");
            return;
        }

        BluetoothGattCharacteristic ssidChar = service.getCharacteristic(CHAR_SSID_UUID);
        if (ssidChar == null) {
            notifyError("SSID characteristic not found.");
            return;
        }

        this.pendingSsid = ssid;
        this.pendingPass = password;

        notifyStatus("Sending Wi-Fi SSID: " + ssid);
        ssidChar.setValue(ssid.getBytes(StandardCharsets.UTF_8));
        bluetoothGatt.writeCharacteristic(ssidChar);
    }

    private void writePasswordInternal(String password) {
        if (bluetoothGatt == null) return;
        BluetoothGattService service = bluetoothGatt.getService(SERVICE_UUID);
        if (service == null) return;

        BluetoothGattCharacteristic passChar = service.getCharacteristic(CHAR_PASS_UUID);
        if (passChar != null) {
            notifyStatus("Sending Wi-Fi password...");
            passChar.setValue(password.getBytes(StandardCharsets.UTF_8));
            bluetoothGatt.writeCharacteristic(passChar);
        }
    }

    private void notifyStatus(String msg) {
        mainHandler.post(() -> {
            if (listener != null) listener.onStatusReceived(msg);
        });
    }

    private void notifyError(String err) {
        mainHandler.post(() -> {
            if (listener != null) listener.onError(err);
        });
    }
}

