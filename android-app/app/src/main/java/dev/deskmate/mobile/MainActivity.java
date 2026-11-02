package dev.deskmate.mobile;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONArray;
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
    private static final int REQ_ENABLE_BT = 1002;
    private static final String PREFS_NAME = "deskmate_prefs";
    private static final String KEY_BACKEND_HOST = "backend_host";
    private static final String KEY_DEVICE_ID = "device_id";

    // Top Header & Banners
    private TextView badgeStatus;
    private LinearLayout bannerBluetooth;
    private Button btnEnableBluetooth;

    // Tabs
    private Button tabChat, tabDevice, tabFocus, tabTasks;
    private View panelChat, panelDevice, panelFocus, panelTasks;

    // Page 1: AI Chat
    private ScrollView scrollChat;
    private LinearLayout containerChatMessages;
    private EditText etChatMessage;
    private Button btnSendMessage;
    private TextView tvTypingIndicator;
    private TextView chipStartFocus, chipToggleLamp;

    // Page 2: Assistant & BLE
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

    // Page 3: Focus & Pomodoro
    private TextView tvFocusCountdown, tvFocusSessionLabel;
    private Button btnPreset5, btnPreset15, btnPreset25;
    private Button btnStartFocus;
    private TextView tvFocusMinutes, tvFocusCycles, tvFocusStreak;

    // Page 4: Tasks & League
    private EditText etNewTask;
    private Button btnAddTask;
    private LinearLayout containerTasksList;
    private TextView tvEmptyTasks;
    private TextView tvCompetitionCode;
    private Button btnCopyCode;

    // Services & State
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
        setupChatbot();
        setupBleControls();
        setupHardwareControls();
        setupFocusControls();
        setupTasksAndLeague();

        checkAndRequestPermissions();
        checkBluetoothState(true);
        updateOledClock();
        loadRecentTasks();
    }

    @Override
    protected void onResume() {
        super.onResume();
        checkBluetoothState(false);
    }

    private void initViews() {
        badgeStatus = findViewById(R.id.badgeStatus);
        bannerBluetooth = findViewById(R.id.bannerBluetooth);
        btnEnableBluetooth = findViewById(R.id.btnEnableBluetooth);

        tabChat = findViewById(R.id.tabChat);
        tabDevice = findViewById(R.id.tabDevice);
        tabFocus = findViewById(R.id.tabFocus);
        tabTasks = findViewById(R.id.tabTasks);

        panelChat = findViewById(R.id.panelChat);
        panelDevice = findViewById(R.id.panelDevice);
        panelFocus = findViewById(R.id.panelFocus);
        panelTasks = findViewById(R.id.panelTasks);

        // Chat
        scrollChat = findViewById(R.id.scrollChat);
        containerChatMessages = findViewById(R.id.containerChatMessages);
        etChatMessage = findViewById(R.id.etChatMessage);
        btnSendMessage = findViewById(R.id.btnSendMessage);
        tvTypingIndicator = findViewById(R.id.tvTypingIndicator);
        chipStartFocus = findViewById(R.id.chipStartFocus);
        chipToggleLamp = findViewById(R.id.chipToggleLamp);

        // Device & BLE
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

        // Focus
        tvFocusCountdown = findViewById(R.id.tvFocusCountdown);
        tvFocusSessionLabel = findViewById(R.id.tvFocusSessionLabel);
        btnPreset5 = findViewById(R.id.btnPreset5);
        btnPreset15 = findViewById(R.id.btnPreset15);
        btnPreset25 = findViewById(R.id.btnPreset25);
        btnStartFocus = findViewById(R.id.btnStartFocus);
        tvFocusMinutes = findViewById(R.id.tvFocusMinutes);
        tvFocusCycles = findViewById(R.id.tvFocusCycles);
        tvFocusStreak = findViewById(R.id.tvFocusStreak);

        // Tasks & League
        etNewTask = findViewById(R.id.etNewTask);
        btnAddTask = findViewById(R.id.btnAddTask);
        containerTasksList = findViewById(R.id.containerTasksList);
        tvEmptyTasks = findViewById(R.id.tvEmptyTasks);
        tvCompetitionCode = findViewById(R.id.tvCompetitionCode);
        btnCopyCode = findViewById(R.id.btnCopyCode);

        // Load persisted host
        String savedHost = prefs.getString(KEY_BACKEND_HOST, "http://10.0.2.2:8000");
        etBackendHost.setText(savedHost);

        btnEnableBluetooth.setOnClickListener(v -> requestEnableBluetooth());
    }

    private void checkBluetoothState(boolean showDialogIfDisabled) {
        if (!bleManager.isBluetoothEnabled()) {
            bannerBluetooth.setVisibility(View.VISIBLE);
            badgeStatus.setText("BLE: Off");
            badgeStatus.setTextColor(0xFFEF4444);

            if (showDialogIfDisabled) {
                new AlertDialog.Builder(this)
                        .setTitle("Turn on Bluetooth")
                        .setMessage("DeskMate AI Assistant requires Bluetooth to discover and provision your device. Turn on Bluetooth now?")
                        .setPositiveButton("Turn On", (d, w) -> requestEnableBluetooth())
                        .setNegativeButton("Later", null)
                        .show();
            }
        } else {
            bannerBluetooth.setVisibility(View.GONE);
            badgeStatus.setText("BLE: Ready");
            badgeStatus.setTextColor(0xFF2563EB);
        }
    }

    @SuppressLint("MissingPermission")
    private void requestEnableBluetooth() {
        try {
            Intent enableBtIntent = new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE);
            startActivityForResult(enableBtIntent, REQ_ENABLE_BT);
        } catch (Exception e) {
            Toast.makeText(this, "Please enable Bluetooth in Android settings.", Toast.LENGTH_SHORT).show();
        }
    }

    private void setupTabs() {
        tabChat.setOnClickListener(v -> selectTab(0));
        tabDevice.setOnClickListener(v -> selectTab(1));
        tabFocus.setOnClickListener(v -> selectTab(2));
        tabTasks.setOnClickListener(v -> selectTab(3));
    }

    private void selectTab(int index) {
        panelChat.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        panelDevice.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        panelFocus.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        panelTasks.setVisibility(index == 3 ? View.VISIBLE : View.GONE);

        updateTabStyle(tabChat, index == 0);
        updateTabStyle(tabDevice, index == 1);
        updateTabStyle(tabFocus, index == 2);
        updateTabStyle(tabTasks, index == 3);
    }

    private void updateTabStyle(Button btn, boolean selected) {
        btn.setBackgroundResource(selected ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btn.setTextColor(selected ? 0xFFFFFFFF : 0xFF0F172A);
    }

    // ========================================================
    // 💬 AI CHATBOT IMPLEMENTATION
    // ========================================================

    private void setupChatbot() {
        btnSendMessage.setOnClickListener(v -> {
            String text = etChatMessage.getText().toString().trim();
            if (text.isEmpty()) return;
            etChatMessage.setText("");
            sendChatMessage(text);
        });

        chipStartFocus.setOnClickListener(v -> {
            selectTab(2); // Switch to Focus tab
            startFocusTimer();
        });

        chipToggleLamp.setOnClickListener(v -> toggleLampState());
    }

    private void sendChatMessage(String userMessage) {
        // Add user bubble
        addChatBubble(userMessage, true);

        tvTypingIndicator.setVisibility(View.VISIBLE);
        scrollChatToBottom();

        String host = getBackendHost();
        String url = host + "/api/chat?device_id=deskmate-01";

        try {
            JSONObject payload = new JSONObject();
            payload.put("message", userMessage);
            payload.put("source", "mobile");
            payload.put("speak", false);

            backendClient.post(url, payload, new BackendClient.JsonObjectCallback() {
                @Override
                public void onSuccess(JSONObject response) {
                    tvTypingIndicator.setVisibility(View.GONE);
                    String reply = response.optString("reply", "Done!");
                    addChatBubble(reply, false);

                    // If backend took an action (e.g. toggled relay lamp)
                    String action = response.optString("action_taken", "");
                    if (action.contains("relay") || action.contains("light") || action.contains("lamp")) {
                        isLampOn = !isLampOn;
                        updateLampButtonUI();
                    }
                }

                @Override
                public void onError(String error) {
                    tvTypingIndicator.setVisibility(View.GONE);
                    // Helpful local fallback response
                    String fallback;
                    if (userMessage.toLowerCase().contains("lamp") || userMessage.toLowerCase().contains("light")) {
                        toggleLampState();
                        fallback = "💡 I toggled your Desk Lamp directly!";
                    } else if (userMessage.toLowerCase().contains("focus") || userMessage.toLowerCase().contains("timer")) {
                        selectTab(2);
                        startFocusTimer();
                        fallback = "⏱️ Started a 25-minute Pomodoro study session for you!";
                    } else {
                        fallback = "🤖 (Offline Mode) Make sure backend is running at " + host + ". Meanwhile, you can control your lamp, focus timer, and BLE directly!";
                    }
                    addChatBubble(fallback, false);
                }
            });
        } catch (Exception e) {
            tvTypingIndicator.setVisibility(View.GONE);
            addChatBubble("Error sending message: " + e.getMessage(), false);
        }
    }

    private void addChatBubble(String text, boolean isUser) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(isUser ? Gravity.END : Gravity.START);
        row.setPadding(0, 8, 0, 8);

        TextView bubble = new TextView(this);
        bubble.setText(text);
        bubble.setTextSize(13);
        bubble.setLineSpacing(2, 1.2f);
        bubble.setPadding(32, 24, 32, 24);

        if (isUser) {
            bubble.setBackgroundResource(R.drawable.chat_bubble_user);
            bubble.setTextColor(Color.WHITE);
        } else {
            bubble.setBackgroundResource(R.drawable.chat_bubble_bot);
            bubble.setTextColor(0xFF0F172A);
        }

        // Limit bubble width to 80% screen
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.width = (int) (getResources().getDisplayMetrics().widthPixels * 0.78);
        bubble.setLayoutParams(params);

        row.addView(bubble);
        containerChatMessages.addView(row);
        scrollChatToBottom();
    }

    private void scrollChatToBottom() {
        scrollChat.post(() -> scrollChat.fullScroll(View.FOCUS_DOWN));
    }

    // ========================================================
    // 🖥️ ASSISTANT & BLE PROVISIONING
    // ========================================================

    private void setupBleControls() {
        btnBleScan.setOnClickListener(v -> {
            if (!hasRequiredPermissions()) {
                checkAndRequestPermissions();
                return;
            }
            if (!bleManager.isBluetoothEnabled()) {
                requestEnableBluetooth();
                return;
            }

            if (bleManager.isScanning()) {
                bleManager.stopScan();
                pbScanning.setVisibility(View.GONE);
                tvBleProgress.setText("Scan cancelled");
            } else {
                pbScanning.setVisibility(View.VISIBLE);
                tvBleProgress.setText("Searching for DeskMate AI Assistant…");
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
            tvBleProgress.setText("Provisioning Wi-Fi to AI Assistant…");
            bleManager.provisionWifi(ssid, pass);
        });
    }

    private void setupHardwareControls() {
        btnToggleRelay.setOnClickListener(v -> toggleLampState());

        btnSyncDevice.setOnClickListener(v -> syncDeviceState());

        btnSaveHost.setOnClickListener(v -> {
            String host = etBackendHost.getText().toString().trim();
            prefs.edit().putString(KEY_BACKEND_HOST, host).apply();
            Toast.makeText(this, "Saved: " + host, Toast.LENGTH_SHORT).show();
            syncDeviceState();
        });
    }

    private void toggleLampState() {
        isLampOn = !isLampOn;
        updateLampButtonUI();

        String host = getBackendHost();
        try {
            JSONObject payload = new JSONObject();
            payload.put("state", isLampOn);
            backendClient.post(host + "/api/device/relay", payload, new BackendClient.JsonObjectCallback() {
                @Override
                public void onSuccess(JSONObject response) {
                    Toast.makeText(MainActivity.this, "Lamp " + (isLampOn ? "ON" : "OFF"), Toast.LENGTH_SHORT).show();
                }
                @Override
                public void onError(String error) {}
            });
        } catch (Exception ignored) {}
    }

    private void updateLampButtonUI() {
        btnToggleRelay.setText(isLampOn ? "💡 Lamp: ON" : "💡 Lamp: OFF");
        btnToggleRelay.setBackgroundResource(isLampOn ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btnToggleRelay.setTextColor(isLampOn ? 0xFFFFFFFF : 0xFF0F172A);
    }

    private void syncDeviceState() {
        String host = getBackendHost();
        tvOledMode.setText("Syncing with backend…");
        backendClient.getObject(host + "/api/device/status", new BackendClient.JsonObjectCallback() {
            @Override
            public void onSuccess(JSONObject response) {
                tvOledMode.setText("DeskMate AI Synced: OK");
                badgeStatus.setText("Online");
                badgeStatus.setTextColor(0xFF059669);
                Toast.makeText(MainActivity.this, "Assistant status synced!", Toast.LENGTH_SHORT).show();
            }
            @Override
            public void onError(String error) {
                tvOledMode.setText("Offline (Local BLE Active)");
            }
        });
    }

    private String getBackendHost() {
        return etBackendHost.getText().toString().trim();
    }

    // ========================================================
    // ⏱️ FOCUS & POMODORO
    // ========================================================

    private void setupFocusControls() {
        btnPreset5.setOnClickListener(v -> setFocusPreset(5));
        btnPreset15.setOnClickListener(v -> setFocusPreset(15));
        btnPreset25.setOnClickListener(v -> setFocusPreset(25));

        btnStartFocus.setOnClickListener(v -> {
            if (isFocusRunning) stopFocusTimer();
            else startFocusTimer();
        });
    }

    private void setFocusPreset(int minutes) {
        if (isFocusRunning) return;
        selectedFocusMin = minutes;
        focusRemainingSec = minutes * 60;
        updateFocusDisplay();

        updateTabStyle(btnPreset5, minutes == 5);
        updateTabStyle(btnPreset15, minutes == 15);
        updateTabStyle(btnPreset25, minutes == 25);
    }

    private void startFocusTimer() {
        isFocusRunning = true;
        btnStartFocus.setText("⏹ Stop Focus Session");
        btnStartFocus.setBackgroundResource(R.drawable.btn_secondary);
        btnStartFocus.setTextColor(0xFFEF4444);
        tvFocusSessionLabel.setText("Focusing… DeskMate OLED in sync");
        tvOledMode.setText("Mode: Pomodoro Active");

        // Sync with backend
        String host = getBackendHost();
        try {
            JSONObject payload = new JSONObject();
            payload.put("duration_minutes", selectedFocusMin);
            backendClient.post(host + "/api/pomodoro/start", payload, new BackendClient.JsonObjectCallback() {
                @Override public void onSuccess(JSONObject response) {}
                @Override public void onError(String error) {}
            });
        } catch (Exception ignored) {}

        timerHandler.postDelayed(focusRunnable, 1000);
    }

    private void stopFocusTimer() {
        isFocusRunning = false;
        timerHandler.removeCallbacks(focusRunnable);
        btnStartFocus.setText("▶ Start Focus Session");
        btnStartFocus.setBackgroundResource(R.drawable.btn_primary);
        btnStartFocus.setTextColor(0xFFFFFFFF);
        tvFocusSessionLabel.setText("Session Paused");
        tvOledMode.setText("Mode: AI Assistant Ready");

        // Sync with backend
        String host = getBackendHost();
        backendClient.post(host + "/api/pomodoro/stop", new JSONObject(), new BackendClient.JsonObjectCallback() {
            @Override public void onSuccess(JSONObject response) {}
            @Override public void onError(String error) {}
        });
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
                Toast.makeText(MainActivity.this, "🎉 Pomodoro complete! Great study session.", Toast.LENGTH_LONG).show();
            }
        }
    };

    private void updateFocusDisplay() {
        int m = focusRemainingSec / 60;
        int s = focusRemainingSec % 60;
        tvFocusCountdown.setText(String.format(Locale.US, "%02d:%02d", m, s));
    }

    // ========================================================
    // 📋 TASKS & STUDY LEAGUE
    // ========================================================

    private void setupTasksAndLeague() {
        btnAddTask.setOnClickListener(v -> {
            String title = etNewTask.getText().toString().trim();
            if (title.isEmpty()) return;
            etNewTask.setText("");
            createStudyTask(title);
        });

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

    private void createStudyTask(String title) {
        String host = getBackendHost();
        String url = host + "/api/tasks?device_id=deskmate-01";

        try {
            JSONObject payload = new JSONObject();
            payload.put("title", title);

            backendClient.post(url, payload, new BackendClient.JsonObjectCallback() {
                @Override
                public void onSuccess(JSONObject response) {
                    Toast.makeText(MainActivity.this, "Task added!", Toast.LENGTH_SHORT).show();
                    loadRecentTasks();
                }

                @Override
                public void onError(String error) {
                    // Offline add
                    addTaskRowLocally(title, false);
                }
            });
        } catch (Exception e) {
            addTaskRowLocally(title, false);
        }
    }

    private void loadRecentTasks() {
        String host = getBackendHost();
        String url = host + "/api/tasks?device_id=deskmate-01";

        backendClient.getArray(url, new BackendClient.JsonArrayCallback() {
            @Override
            public void onSuccess(JSONArray response) {
                if (response.length() > 0) {
                    tvEmptyTasks.setVisibility(View.GONE);
                    containerTasksList.removeAllViews();
                    for (int i = 0; i < response.length(); i++) {
                        JSONObject task = response.optJSONObject(i);
                        if (task != null) {
                            String title = task.optString("title", "Study Task");
                            boolean done = task.optBoolean("done", false);
                            addTaskRowLocally(title, done);
                        }
                    }
                }
            }

            @Override
            public void onError(String error) {}
        });
    }

    private void addTaskRowLocally(String title, boolean done) {
        tvEmptyTasks.setVisibility(View.GONE);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackgroundResource(R.drawable.btn_secondary);
        row.setPadding(24, 16, 24, 16);

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, 0, 0, 12);
        row.setLayoutParams(params);

        CheckBox cb = new CheckBox(this);
        cb.setChecked(done);
        cb.setText(title);
        cb.setTextColor(0xFF0F172A);
        cb.setTextSize(13);

        row.addView(cb);
        containerTasksList.addView(row, 0);
    }

    private void updateOledClock() {
        SimpleDateFormat sdf = new SimpleDateFormat("HH:mm", Locale.getDefault());
        tvOledTime.setText(sdf.format(new Date()));
        timerHandler.postDelayed(this::updateOledClock, 10000);
    }

    // ========================================================
    // 📡 BLE LISTENER CALLBACKS
    // ========================================================

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
            badgeStatus.setText("BLE: Connected");
            badgeStatus.setTextColor(0xFF059669);
            tvBleProgress.setText("Connected to " + deviceName);
            layoutWifiForm.setVisibility(View.VISIBLE);
            tvOledStatus.setText("WIFI: Config Pending | BLE: OK");
            Toast.makeText(this, "Paired with " + deviceName + "! Enter Wi-Fi below.", Toast.LENGTH_SHORT).show();
        } else {
            badgeStatus.setText("BLE: Ready");
            badgeStatus.setTextColor(0xFF2563EB);
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
        badgeStatus.setText("Online (" + assignedIp + ")");
        badgeStatus.setTextColor(0xFF059669);

        // Auto-configure backend host to match the new subnet
        String newHost = "http://" + assignedIp + ":8000";
        etBackendHost.setText(newHost);
        prefs.edit().putString(KEY_BACKEND_HOST, newHost).apply();

        new AlertDialog.Builder(this)
                .setTitle("🎉 Wi-Fi Connected!")
                .setMessage("Your DeskMate AI Assistant is now connected to your Wi-Fi network at IP " + assignedIp + ".\n\nYou can now chat with your AI assistant and control it seamlessly.")
                .setPositiveButton("Start Chatting", (d, w) -> selectTab(0))
                .setNegativeButton("OK", null)
                .show();
    }

    @Override
    public void onError(String message) {
        pbScanning.setVisibility(View.GONE);
        tvBleProgress.setText(message);
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    // ========================================================
    // 🔒 PERMISSIONS
    // ========================================================

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
