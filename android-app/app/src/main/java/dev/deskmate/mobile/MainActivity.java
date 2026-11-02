package dev.deskmate.mobile;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import dev.deskmate.mobile.api.BackendClient;
import dev.deskmate.mobile.ble.DeskMateBleManager;
import dev.deskmate.mobile.ble.DiscoveredBleDevice;

@SuppressLint("SetTextI18n")
public class MainActivity extends AppCompatActivity implements DeskMateBleManager.BleListener {

    private static final int REQ_PERMISSIONS = 1001;
    private static final String PREFS_NAME = "deskmate_prefs";
    private static final String KEY_BACKEND_HOST = "backend_host";

    // UI elements
    private TextView badgeBleStatus;
    private Button tabDevice, tabFocus, tabLeague;
    private LinearLayout panelDevice, panelFocus, panelLeague;

    // Tab 1: Device & BLE
    private Button btnBleScan;
    private ProgressBar pbScanning;
    private TextView tvBleProgress;
    private LinearLayout containerDiscoveredDevice;
    private TextView tvDiscoveredName, tvDiscoveredMac;
    private Button btnConnectDevice;
    private LinearLayout layoutWifiForm;
    private EditText etWifiSsid, etWifiPass;
    private Button btnSendWifi;

    private TextView tvOledTime, tvOledStatus, tvOledMode;
    private Button btnToggleRelay, btnSyncDevice;
    private EditText etBackendHost;
    private Button btnSaveHost;

    // Tab 2: Focus
    private TextView tvFocusCountdown, tvFocusSessionLabel;
    private Button btnPreset5, btnPreset15, btnPreset25;
    private Button btnStartFocus;
    private TextView tvFocusMinutes, tvFocusCycles, tvFocusStreak;

    // Tab 3: League
    private TextView tvCompetitionCode;
    private Button btnCopyCode;

    // Logic & Services
    private DeskMateBleManager bleManager;
    private BackendClient backendClient;
    private SharedPreferences prefs;
    private DiscoveredBleDevice discoveredDevice;

    private boolean isLampOn = false;
    private boolean isFocusRunning = false;
    private int focusRemainingSec = 25 * 60;
    private int selectedFocusMin = 25;
    private final Handler timerHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        backendClient = new BackendClient();
        bleManager = new DeskMateBleManager(this);
        bleManager.setListener(this);

        initViews();
        setupTabs();
        setupBleControls();
        setupHardwareControls();
        setupFocusControls();
        setupLeagueControls();

        checkAndRequestPermissions();
        updateOledClock();
    }

    private void initViews() {
        badgeBleStatus = findViewById(R.id.badgeBleStatus);
        tabDevice = findViewById(R.id.tabDevice);
        tabFocus = findViewById(R.id.tabFocus);
        tabLeague = findViewById(R.id.tabLeague);

        panelDevice = findViewById(R.id.panelDevice);
        panelFocus = findViewById(R.id.panelFocus);
        panelLeague = findViewById(R.id.panelLeague);

        btnBleScan = findViewById(R.id.btnBleScan);
        pbScanning = findViewById(R.id.pbScanning);
        tvBleProgress = findViewById(R.id.tvBleProgress);
        containerDiscoveredDevice = findViewById(R.id.containerDiscoveredDevice);
        tvDiscoveredName = findViewById(R.id.tvDiscoveredName);
        tvDiscoveredMac = findViewById(R.id.tvDiscoveredMac);
        btnConnectDevice = findViewById(R.id.btnConnectDevice);

        layoutWifiForm = findViewById(R.id.layoutWifiForm);
        etWifiSsid = findViewById(R.id.etWifiSsid);
        etWifiPass = findViewById(R.id.etWifiPass);
        btnSendWifi = findViewById(R.id.btnSendWifi);

        tvOledTime = findViewById(R.id.tvOledTime);
        tvOledStatus = findViewById(R.id.tvOledStatus);
        tvOledMode = findViewById(R.id.tvOledMode);
        btnToggleRelay = findViewById(R.id.btnToggleRelay);
        btnSyncDevice = findViewById(R.id.btnSyncDevice);
        etBackendHost = findViewById(R.id.etBackendHost);
        btnSaveHost = findViewById(R.id.btnSaveHost);

        tvFocusCountdown = findViewById(R.id.tvFocusCountdown);
        tvFocusSessionLabel = findViewById(R.id.tvFocusSessionLabel);
        btnPreset5 = findViewById(R.id.btnPreset5);
        btnPreset15 = findViewById(R.id.btnPreset15);
        btnPreset25 = findViewById(R.id.btnPreset25);
        btnStartFocus = findViewById(R.id.btnStartFocus);
        tvFocusMinutes = findViewById(R.id.tvFocusMinutes);
        tvFocusCycles = findViewById(R.id.tvFocusCycles);
        tvFocusStreak = findViewById(R.id.tvFocusStreak);

        tvCompetitionCode = findViewById(R.id.tvCompetitionCode);
        btnCopyCode = findViewById(R.id.btnCopyCode);

        // Load stored backend host
        String savedHost = prefs.getString(KEY_BACKEND_HOST, "http://10.0.2.2:8000");
        etBackendHost.setText(savedHost);
    }

    private void setupTabs() {
        tabDevice.setOnClickListener(v -> selectTab(0));
        tabFocus.setOnClickListener(v -> selectTab(1));
        tabLeague.setOnClickListener(v -> selectTab(2));
    }

    private void selectTab(int index) {
        panelDevice.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        panelFocus.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        panelLeague.setVisibility(index == 2 ? View.VISIBLE : View.GONE);

        tabDevice.setBackgroundResource(index == 0 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        tabDevice.setTextColor(index == 0 ? 0xFFFFFFFF : 0xFF0F172A);

        tabFocus.setBackgroundResource(index == 1 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        tabFocus.setTextColor(index == 1 ? 0xFFFFFFFF : 0xFF0F172A);

        tabLeague.setBackgroundResource(index == 2 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        tabLeague.setTextColor(index == 2 ? 0xFFFFFFFF : 0xFF0F172A);
    }

    private void setupBleControls() {
        btnBleScan.setOnClickListener(v -> {
            if (!hasRequiredPermissions()) {
                checkAndRequestPermissions();
                return;
            }
            if (bleManager.isScanning()) {
                bleManager.stopScan();
                pbScanning.setVisibility(View.GONE);
                tvBleProgress.setText("Scan stopped");
            } else {
                pbScanning.setVisibility(View.VISIBLE);
                tvBleProgress.setText("Scanning for DeskMate…");
                containerDiscoveredDevice.setVisibility(View.GONE);
                bleManager.startScan();
            }
        });

        btnConnectDevice.setOnClickListener(v -> {
            if (discoveredDevice != null) {
                tvBleProgress.setText("Connecting to " + discoveredDevice.getName() + "…");
                bleManager.connect(discoveredDevice.getDevice());
            }
        });

        btnSendWifi.setOnClickListener(v -> {
            String ssid = etWifiSsid.getText().toString().trim();
            String pass = etWifiPass.getText().toString().trim();
            if (ssid.isEmpty()) {
                Toast.makeText(this, "Please enter Wi-Fi network name", Toast.LENGTH_SHORT).show();
                return;
            }
            tvBleProgress.setText("Provisioning Wi-Fi…");
            bleManager.provisionWifi(ssid, pass);
        });
    }

    private void setupHardwareControls() {
        btnToggleRelay.setOnClickListener(v -> {
            isLampOn = !isLampOn;
            btnToggleRelay.setText(isLampOn ? "💡 Lamp: ON" : "💡 Lamp: OFF");
            btnToggleRelay.setBackgroundResource(isLampOn ? R.drawable.btn_primary : R.drawable.btn_secondary);
            btnToggleRelay.setTextColor(isLampOn ? 0xFFFFFFFF : 0xFF0F172A);

            String host = etBackendHost.getText().toString().trim();
            try {
                JSONObject payload = new JSONObject();
                payload.put("state", isLampOn);
                backendClient.post(host + "/api/device/relay", payload, new BackendClient.ApiCallback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        Toast.makeText(MainActivity.this, "Lamp " + (isLampOn ? "turned ON" : "turned OFF"), Toast.LENGTH_SHORT).show();
                    }
                    @Override
                    public void onError(String error) {
                        // Keep optimistic UI state
                    }
                });
            } catch (Exception ignored) {}
        });

        btnSyncDevice.setOnClickListener(v -> {
            String host = etBackendHost.getText().toString().trim();
            tvOledMode.setText("Syncing with backend…");
            backendClient.get(host + "/api/device/status", new BackendClient.ApiCallback() {
                @Override
                public void onSuccess(JSONObject response) {
                    tvOledMode.setText("Backend Synced: OK");
                    Toast.makeText(MainActivity.this, "Hardware synced!", Toast.LENGTH_SHORT).show();
                }
                @Override
                public void onError(String error) {
                    tvOledMode.setText("Offline (Local BLE Active)");
                }
            });
        });

        btnSaveHost.setOnClickListener(v -> {
            String host = etBackendHost.getText().toString().trim();
            prefs.edit().putString(KEY_BACKEND_HOST, host).apply();
            Toast.makeText(this, "Backend host saved: " + host, Toast.LENGTH_SHORT).show();
        });
    }

    private void setupFocusControls() {
        btnPreset5.setOnClickListener(v -> setFocusPreset(5));
        btnPreset15.setOnClickListener(v -> setFocusPreset(15));
        btnPreset25.setOnClickListener(v -> setFocusPreset(25));

        btnStartFocus.setOnClickListener(v -> {
            if (isFocusRunning) {
                stopFocusTimer();
            } else {
                startFocusTimer();
            }
        });
    }

    private void setFocusPreset(int minutes) {
        if (isFocusRunning) return;
        selectedFocusMin = minutes;
        focusRemainingSec = minutes * 60;
        updateFocusDisplay();

        btnPreset5.setBackgroundResource(minutes == 5 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btnPreset5.setTextColor(minutes == 5 ? 0xFFFFFFFF : 0xFF0F172A);

        btnPreset15.setBackgroundResource(minutes == 15 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btnPreset15.setTextColor(minutes == 15 ? 0xFFFFFFFF : 0xFF0F172A);

        btnPreset25.setBackgroundResource(minutes == 25 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btnPreset25.setTextColor(minutes == 25 ? 0xFFFFFFFF : 0xFF0F172A);
    }

    private void startFocusTimer() {
        isFocusRunning = true;
        btnStartFocus.setText("⏹ Stop Focus Session");
        btnStartFocus.setBackgroundResource(R.drawable.btn_secondary);
        btnStartFocus.setTextColor(0xFFEF4444);
        tvFocusSessionLabel.setText("Focusing… DeskMate OLED in sync");
        tvOledMode.setText("Mode: Pomodoro Active");

        timerHandler.postDelayed(focusRunnable, 1000);
    }

    private void stopFocusTimer() {
        isFocusRunning = false;
        timerHandler.removeCallbacks(focusRunnable);
        btnStartFocus.setText("▶ Start Focus Session");
        btnStartFocus.setBackgroundResource(R.drawable.btn_primary);
        btnStartFocus.setTextColor(0xFFFFFFFF);
        tvFocusSessionLabel.setText("Session Paused");
        tvOledMode.setText("Mode: Focus Idle");
    }

    private final Runnable focusRunnable = new Runnable() {
        @Override
        public void run() {
            if (focusRemainingSec > 0) {
                focusRemainingSec--;
                updateFocusDisplay();
                timerHandler.postDelayed(this, 1000);
            } else {
                stopFocusTimer();
                Toast.makeText(MainActivity.this, "🎉 Pomodoro cycle complete!", Toast.LENGTH_LONG).show();
            }
        }
    };

    private void updateFocusDisplay() {
        int m = focusRemainingSec / 60;
        int s = focusRemainingSec % 60;
        tvFocusCountdown.setText(String.format(Locale.US, "%02d:%02d", m, s));
    }

    private void setupLeagueControls() {
        btnCopyCode.setOnClickListener(v -> {
            String code = tvCompetitionCode.getText().toString();
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            ClipData clip = ClipData.newPlainText("DeskMate Competition Code", code);
            if (clipboard != null) {
                clipboard.setPrimaryClip(clip);
                Toast.makeText(this, "Copied " + code + " to clipboard!", Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void updateOledClock() {
        SimpleDateFormat sdf = new SimpleDateFormat("HH:mm", Locale.getDefault());
        tvOledTime.setText(sdf.format(new Date()));
        timerHandler.postDelayed(this::updateOledClock, 10000);
    }

    // --- BLE Listener Callbacks ---

    @Override
    public void onDeviceDiscovered(DiscoveredBleDevice device) {
        this.discoveredDevice = device;
        pbScanning.setVisibility(View.GONE);
        tvBleProgress.setText("Discovered: " + device.getName());

        containerDiscoveredDevice.setVisibility(View.VISIBLE);
        tvDiscoveredName.setText(device.getName());
        tvDiscoveredMac.setText("MAC: " + device.getAddress() + " | RSSI: " + device.getRssi() + " dBm");
    }

    @Override
    public void onConnectionStateChange(boolean connected, String deviceName) {
        if (connected) {
            badgeBleStatus.setText("BLE: Connected");
            badgeBleStatus.setTextColor(0xFF059669);
            tvBleProgress.setText("Connected to " + deviceName);
            layoutWifiForm.setVisibility(View.VISIBLE);
            tvOledStatus.setText("WIFI: Config Pending | BLE: OK");
        } else {
            badgeBleStatus.setText("BLE: Disconnected");
            badgeBleStatus.setTextColor(0xFF2563EB);
            tvBleProgress.setText("Disconnected");
            layoutWifiForm.setVisibility(View.GONE);
        }
    }

    @Override
    public void onStatusReceived(String status) {
        tvBleProgress.setText(status);
    }

    @Override
    public void onProvisionSuccess(String assignedIp) {
        tvBleProgress.setText("Connected! IP: " + assignedIp);
        tvOledStatus.setText("WIFI: " + assignedIp + " | USB");
        Toast.makeText(this, "🎉 DeskMate Connected to Wi-Fi!\nIP: " + assignedIp, Toast.LENGTH_LONG).show();

        // Automatically set backend host if on same subnet
        etBackendHost.setText("http://" + assignedIp + ":8000");
    }

    @Override
    public void onError(String message) {
        pbScanning.setVisibility(View.GONE);
        tvBleProgress.setText(message);
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    // --- Permissions ---

    private boolean hasRequiredPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                    && ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        } else {
            return ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        }
    }

    private void checkAndRequestPermissions() {
        List<String> list = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                list.add(Manifest.permission.BLUETOOTH_SCAN);
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                list.add(Manifest.permission.BLUETOOTH_CONNECT);
            }
        } else {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                list.add(Manifest.permission.ACCESS_FINE_LOCATION);
            }
        }

        if (!list.isEmpty()) {
            ActivityCompat.requestPermissions(this, list.toArray(new String[0]), REQ_PERMISSIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_PERMISSIONS) {
            boolean allGranted = true;
            for (int r : grantResults) {
                if (r != PackageManager.PERMISSION_GRANTED) {
                    allGranted = false;
                    break;
                }
            }
            if (!allGranted) {
                Toast.makeText(this, "Bluetooth permissions are required for pairing DeskMate.", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (bleManager != null) {
            bleManager.disconnect();
        }
        timerHandler.removeCallbacksAndMessages(null);
    }
}
