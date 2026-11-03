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
import android.os.SystemClock;
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
    private static final String KEY_USERNAME = "current_username";
    private static final String KEY_DISPLAY_NAME = "current_display_name";
    private static final String KEY_COMP_CODE = "current_comp_code";

    // User Account
    private TextView tvActiveUserInfo, tvActiveUserCode;
    private Button btnSwitchAccount;

    // Top Header & Banners
    private TextView badgeStatus;
    private Button btnOpenSettings;
    private LinearLayout bannerBluetooth;
    private Button btnEnableBluetooth;

    // Bottom Navigation Bar & Tabs
    private LinearLayout bottomNavBar;
    private LinearLayout navHome, navChat, navFocus, navStudy, navLeague;
    private TextView labelNavHome, labelNavChat, labelNavFocus, labelNavStudy, labelNavLeague;

    // Pages
    private View pageHome, pageChat, pageFocus, pageStudy, pageLeague, pageSettings;
    private int currentTab = 0; // 0=Home, 1=Chat, 2=Focus, 3=Study, 4=League

    // Page 1: Home
    private TextView quickLamp, quickFocus25, quickChat, quickStopwatch, quickAlarms, quickLeague;
    private TextView tvOledTime, tvOledStatus, tvOledMode;
    private Button btnToggleRelay, btnSyncDevice, btnQuickStartFocus;
    private TextView tvMetricsFocus, tvMetricsCycles, tvMetricsTasks, tvMetricsStreak;

    // Page 2: Chat
    private ScrollView scrollChat;
    private LinearLayout containerChatMessages;
    private EditText etChatMessage;
    private Button btnSendMessage;
    private TextView tvTypingIndicator;
    private TextView chipStartFocus, chipToggleLamp;

    // Page 3: Focus & Productivity Hub
    private TextView subTabPomodoro, subTabTimer, subTabStopwatch, subTabAlarms, subTabReminders;
    private View sectionPomodoro, sectionStopwatch, sectionAlarms, sectionReminders;
    private TextView tvFocusCountdown, tvFocusSessionLabel;
    private Button btnPreset5, btnPreset15, btnPreset25, btnPreset45, btnStartFocus;

    // Stopwatch Sub-tool
    private TextView tvStopwatchTime, tvStopwatchLaps;
    private Button btnStartStopwatch, btnLapStopwatch, btnResetStopwatch;
    private boolean isStopwatchRunning = false;
    private long stopwatchBaseTime = 0;
    private long stopwatchTimeBuff = 0;
    private int lapCounter = 1;

    // Page 4: Study & Tasks
    private TextView subTabTasks, subTabNotes, subTabAnalytics;
    private View sectionTasks, sectionNotes, sectionAnalytics;
    private EditText etNewTask;
    private Button btnAddTask, btnQuizNotes;
    private LinearLayout containerTasksList;
    private TextView tvEmptyTasks;

    // Page 5: League
    private TextView tvCompetitionCode;
    private Button btnCopyCode;

    // Page 6: Settings (Dedicated Page)
    private Button btnCloseSettings;
    private Button btnBleScan;
    private ProgressBar pbScanning;
    private TextView tvBleProgress;
    private LinearLayout containerDiscoveredDevice;
    private TextView tvDiscoveredName, tvDiscoveredMac;
    private Button btnConnectDevice;
    private LinearLayout layoutWifiForm;
    private EditText etWifiSsid, etWifiPass;
    private Button btnSendWifi;
    private EditText etBackendHost;
    private Button btnSaveHost;

    // Logic, BLE & Handlers
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
        setupBottomNavigation();
        setupQuickCarousel();
        setupChatbot();
        setupFocusHub();
        setupStopwatch();
        setupStudyHub();
        setupSettingsAndBle();

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
        btnOpenSettings = findViewById(R.id.btnOpenSettings);
        bannerBluetooth = findViewById(R.id.bannerBluetooth);
        btnEnableBluetooth = findViewById(R.id.btnEnableBluetooth);

        bottomNavBar = findViewById(R.id.bottomNavBar);
        navHome = findViewById(R.id.navHome);
        navChat = findViewById(R.id.navChat);
        navFocus = findViewById(R.id.navFocus);
        navStudy = findViewById(R.id.navStudy);
        navLeague = findViewById(R.id.navLeague);

        labelNavHome = findViewById(R.id.labelNavHome);
        labelNavChat = findViewById(R.id.labelNavChat);
        labelNavFocus = findViewById(R.id.labelNavFocus);
        labelNavStudy = findViewById(R.id.labelNavStudy);
        labelNavLeague = findViewById(R.id.labelNavLeague);

        pageHome = findViewById(R.id.pageHome);
        pageChat = findViewById(R.id.pageChat);
        pageFocus = findViewById(R.id.pageFocus);
        pageStudy = findViewById(R.id.pageStudy);
        pageLeague = findViewById(R.id.pageLeague);
        pageSettings = findViewById(R.id.pageSettings);

        // Home
        quickLamp = findViewById(R.id.quickLamp);
        quickFocus25 = findViewById(R.id.quickFocus25);
        quickChat = findViewById(R.id.quickChat);
        quickStopwatch = findViewById(R.id.quickStopwatch);
        quickAlarms = findViewById(R.id.quickAlarms);
        quickLeague = findViewById(R.id.quickLeague);

        tvOledTime = findViewById(R.id.tvOledTime);
        tvOledStatus = findViewById(R.id.tvOledStatus);
        tvOledMode = findViewById(R.id.tvOledMode);
        btnToggleRelay = findViewById(R.id.btnToggleRelay);
        btnSyncDevice = findViewById(R.id.btnSyncDevice);
        btnQuickStartFocus = findViewById(R.id.btnQuickStartFocus);

        tvMetricsFocus = findViewById(R.id.tvMetricsFocus);
        tvMetricsCycles = findViewById(R.id.tvMetricsCycles);
        tvMetricsTasks = findViewById(R.id.tvMetricsTasks);
        tvMetricsStreak = findViewById(R.id.tvMetricsStreak);

        // Chat
        scrollChat = findViewById(R.id.scrollChat);
        containerChatMessages = findViewById(R.id.containerChatMessages);
        etChatMessage = findViewById(R.id.etChatMessage);
        btnSendMessage = findViewById(R.id.btnSendMessage);
        tvTypingIndicator = findViewById(R.id.tvTypingIndicator);
        chipStartFocus = findViewById(R.id.chipStartFocus);
        chipToggleLamp = findViewById(R.id.chipToggleLamp);

        // Focus
        subTabPomodoro = findViewById(R.id.subTabPomodoro);
        subTabTimer = findViewById(R.id.subTabTimer);
        subTabStopwatch = findViewById(R.id.subTabStopwatch);
        subTabAlarms = findViewById(R.id.subTabAlarms);
        subTabReminders = findViewById(R.id.subTabReminders);

        sectionPomodoro = findViewById(R.id.sectionPomodoro);
        sectionStopwatch = findViewById(R.id.sectionStopwatch);
        sectionAlarms = findViewById(R.id.sectionAlarms);
        sectionReminders = findViewById(R.id.sectionReminders);

        tvFocusCountdown = findViewById(R.id.tvFocusCountdown);
        tvFocusSessionLabel = findViewById(R.id.tvFocusSessionLabel);
        btnPreset5 = findViewById(R.id.btnPreset5);
        btnPreset15 = findViewById(R.id.btnPreset15);
        btnPreset25 = findViewById(R.id.btnPreset25);
        btnPreset45 = findViewById(R.id.btnPreset45);
        btnStartFocus = findViewById(R.id.btnStartFocus);

        tvStopwatchTime = findViewById(R.id.tvStopwatchTime);
        tvStopwatchLaps = findViewById(R.id.tvStopwatchLaps);
        btnStartStopwatch = findViewById(R.id.btnStartStopwatch);
        btnLapStopwatch = findViewById(R.id.btnLapStopwatch);
        btnResetStopwatch = findViewById(R.id.btnResetStopwatch);

        // Study
        subTabTasks = findViewById(R.id.subTabTasks);
        subTabNotes = findViewById(R.id.subTabNotes);
        subTabAnalytics = findViewById(R.id.subTabAnalytics);

        sectionTasks = findViewById(R.id.sectionTasks);
        sectionNotes = findViewById(R.id.sectionNotes);
        sectionAnalytics = findViewById(R.id.sectionAnalytics);

        etNewTask = findViewById(R.id.etNewTask);
        btnAddTask = findViewById(R.id.btnAddTask);
        btnQuizNotes = findViewById(R.id.btnQuizNotes);
        containerTasksList = findViewById(R.id.containerTasksList);
        tvEmptyTasks = findViewById(R.id.tvEmptyTasks);

        // League
        tvCompetitionCode = findViewById(R.id.tvCompetitionCode);
        btnCopyCode = findViewById(R.id.btnCopyCode);

        // Settings
        btnCloseSettings = findViewById(R.id.btnCloseSettings);
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

        etBackendHost = findViewById(R.id.etBackendHost);
        btnSaveHost = findViewById(R.id.btnSaveHost);

        tvActiveUserInfo = findViewById(R.id.tvActiveUserInfo);
        tvActiveUserCode = findViewById(R.id.tvActiveUserCode);
        btnSwitchAccount = findViewById(R.id.btnSwitchAccount);

        String savedHost = prefs.getString(KEY_BACKEND_HOST, "http://10.0.2.2:8000");
        etBackendHost.setText(savedHost);

        backendClient.setUsername(getActiveUsername());
        updateUserUI();

        btnEnableBluetooth.setOnClickListener(v -> requestEnableBluetooth());
        btnSwitchAccount.setOnClickListener(v -> showAccountSwitchDialog());
    }

    // ========================================================
    // 🧭 BOTTOM NAVIGATION (Zomato / Blinkit Style)
    // ========================================================

    private void setupBottomNavigation() {
        navHome.setOnClickListener(v -> selectTab(0));
        navChat.setOnClickListener(v -> selectTab(1));
        navFocus.setOnClickListener(v -> selectTab(2));
        navStudy.setOnClickListener(v -> selectTab(3));
        navLeague.setOnClickListener(v -> selectTab(4));

        btnOpenSettings.setOnClickListener(v -> openSettingsPage());
        btnCloseSettings.setOnClickListener(v -> closeSettingsPage());
    }

    private void selectTab(int index) {
        currentTab = index;
        pageSettings.setVisibility(View.GONE);
        bottomNavBar.setVisibility(View.VISIBLE);

        pageHome.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        pageChat.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        pageFocus.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        pageStudy.setVisibility(index == 3 ? View.VISIBLE : View.GONE);
        pageLeague.setVisibility(index == 4 ? View.VISIBLE : View.GONE);

        updateNavItem(navHome, labelNavHome, index == 0);
        updateNavItem(navChat, labelNavChat, index == 1);
        updateNavItem(navFocus, labelNavFocus, index == 2);
        updateNavItem(navStudy, labelNavStudy, index == 3);
        updateNavItem(navLeague, labelNavLeague, index == 4);
    }

    private void updateNavItem(LinearLayout navLayout, TextView label, boolean active) {
        navLayout.setBackgroundResource(active ? R.drawable.pill_nav_active : 0);
        label.setTextColor(active ? 0xFF2563EB : 0xFF64748B);
        label.setTextSize(active ? 12 : 11);
    }

    private void openSettingsPage() {
        pageHome.setVisibility(View.GONE);
        pageChat.setVisibility(View.GONE);
        pageFocus.setVisibility(View.GONE);
        pageStudy.setVisibility(View.GONE);
        pageLeague.setVisibility(View.GONE);

        pageSettings.setVisibility(View.VISIBLE);
        bottomNavBar.setVisibility(View.GONE);
    }

    private void closeSettingsPage() {
        selectTab(currentTab);
    }

    // ========================================================
    // ⚡ QUICK ACTION CAROUSEL (HOME PAGE)
    // ========================================================

    private void setupQuickCarousel() {
        quickLamp.setOnClickListener(v -> toggleLampState());

        quickFocus25.setOnClickListener(v -> {
            selectTab(2);
            switchFocusSubTool(0);
            setFocusPreset(25);
            startFocusTimer();
        });

        quickChat.setOnClickListener(v -> selectTab(1));

        quickStopwatch.setOnClickListener(v -> {
            selectTab(2);
            switchFocusSubTool(1);
        });

        quickAlarms.setOnClickListener(v -> {
            selectTab(2);
            switchFocusSubTool(2);
        });

        quickLeague.setOnClickListener(v -> selectTab(4));

        btnToggleRelay.setOnClickListener(v -> toggleLampState());
        btnSyncDevice.setOnClickListener(v -> syncDeviceState());

        btnQuickStartFocus.setOnClickListener(v -> {
            selectTab(2);
            switchFocusSubTool(0);
            startFocusTimer();
        });
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
            selectTab(2);
            switchFocusSubTool(0);
            startFocusTimer();
        });

        chipToggleLamp.setOnClickListener(v -> toggleLampState());
    }

    private void sendChatMessage(String userMessage) {
        addChatBubble(userMessage, true);
        tvTypingIndicator.setVisibility(View.VISIBLE);
        scrollChatToBottom();

        String host = getBackendHost();
        String url = host + "/api/chat?username=" + getActiveUsername();

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

                    String action = response.optString("action_taken", "");
                    if (action.contains("relay") || action.contains("light") || action.contains("lamp")) {
                        isLampOn = !isLampOn;
                        updateLampButtonUI();
                    }
                }

                @Override
                public void onError(String error) {
                    tvTypingIndicator.setVisibility(View.GONE);
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
    // ⏱️ FOCUS & PRODUCTIVITY HUB
    // ========================================================

    private void setupFocusHub() {
        subTabPomodoro.setOnClickListener(v -> switchFocusSubTool(0));
        subTabTimer.setOnClickListener(v -> switchFocusSubTool(0)); // Shared timer engine
        subTabStopwatch.setOnClickListener(v -> switchFocusSubTool(1));
        subTabAlarms.setOnClickListener(v -> switchFocusSubTool(2));
        subTabReminders.setOnClickListener(v -> switchFocusSubTool(3));

        btnPreset5.setOnClickListener(v -> setFocusPreset(5));
        btnPreset15.setOnClickListener(v -> setFocusPreset(15));
        btnPreset25.setOnClickListener(v -> setFocusPreset(25));
        btnPreset45.setOnClickListener(v -> setFocusPreset(45));

        btnStartFocus.setOnClickListener(v -> {
            if (isFocusRunning) stopFocusTimer();
            else startFocusTimer();
        });
    }

    private void switchFocusSubTool(int toolIndex) {
        sectionPomodoro.setVisibility(toolIndex == 0 ? View.VISIBLE : View.GONE);
        sectionStopwatch.setVisibility(toolIndex == 1 ? View.VISIBLE : View.GONE);
        sectionAlarms.setVisibility(toolIndex == 2 ? View.VISIBLE : View.GONE);
        sectionReminders.setVisibility(toolIndex == 3 ? View.VISIBLE : View.GONE);

        updateSubChipStyle(subTabPomodoro, toolIndex == 0);
        updateSubChipStyle(subTabStopwatch, toolIndex == 1);
        updateSubChipStyle(subTabAlarms, toolIndex == 2);
        updateSubChipStyle(subTabReminders, toolIndex == 3);
    }

    private void updateSubChipStyle(TextView chip, boolean active) {
        chip.setBackgroundResource(active ? R.drawable.chip_active_bg : R.drawable.chip_bg);
        chip.setTextColor(active ? 0xFFFFFFFF : 0xFF0F172A);
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

        btnPreset45.setBackgroundResource(minutes == 45 ? R.drawable.btn_primary : R.drawable.btn_secondary);
        btnPreset45.setTextColor(minutes == 45 ? 0xFFFFFFFF : 0xFF0F172A);
    }

    private void startFocusTimer() {
        isFocusRunning = true;
        btnStartFocus.setText("⏹ Stop Focus Session");
        btnStartFocus.setBackgroundResource(R.drawable.btn_secondary);
        btnStartFocus.setTextColor(0xFFEF4444);
        tvFocusSessionLabel.setText("Focusing… DeskMate OLED in sync");
        tvOledMode.setText("Mode: Pomodoro Active");

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
                Toast.makeText(MainActivity.this, "🎉 Pomodoro cycle complete!", Toast.LENGTH_LONG).show();
            }
        }
    };

    private void updateFocusDisplay() {
        int m = focusRemainingSec / 60;
        int s = focusRemainingSec % 60;
        tvFocusCountdown.setText(String.format(Locale.US, "%02d:%02d", m, s));
    }

    // ========================================================
    // ⏱️ STOPWATCH SUB-TOOL
    // ========================================================

    private void setupStopwatch() {
        btnStartStopwatch.setOnClickListener(v -> {
            if (isStopwatchRunning) {
                // Pause
                isStopwatchRunning = false;
                stopwatchTimeBuff += SystemClock.uptimeMillis() - stopwatchBaseTime;
                timerHandler.removeCallbacks(stopwatchRunnable);
                btnStartStopwatch.setText("Resume");
            } else {
                // Start
                isStopwatchRunning = true;
                stopwatchBaseTime = SystemClock.uptimeMillis();
                timerHandler.postDelayed(stopwatchRunnable, 0);
                btnStartStopwatch.setText("Pause");
            }
        });

        btnLapStopwatch.setOnClickListener(v -> {
            if (isStopwatchRunning) {
                String cur = tvStopwatchTime.getText().toString();
                String prev = tvStopwatchLaps.getText().toString();
                if (prev.contains("will appear")) prev = "";
                tvStopwatchLaps.setText("Lap " + lapCounter++ + ": " + cur + "\n" + prev);
            }
        });

        btnResetStopwatch.setOnClickListener(v -> {
            isStopwatchRunning = false;
            stopwatchBaseTime = 0;
            stopwatchTimeBuff = 0;
            lapCounter = 1;
            timerHandler.removeCallbacks(stopwatchRunnable);
            tvStopwatchTime.setText("00:00.00");
            tvStopwatchLaps.setText("Laps will appear here");
            btnStartStopwatch.setText("Start");
        });
    }

    private final Runnable stopwatchRunnable = new Runnable() {
        @Override
        public void run() {
            long timeInMs = SystemClock.uptimeMillis() - stopwatchBaseTime;
            long updatedTime = stopwatchTimeBuff + timeInMs;
            int secs = (int) (updatedTime / 1000);
            int mins = secs / 60;
            secs = secs % 60;
            int ms = (int) ((updatedTime % 1000) / 10);
            tvStopwatchTime.setText(String.format(Locale.US, "%02d:%02d.%02d", mins, secs, ms));
            timerHandler.postDelayed(this, 30);
        }
    };

    // ========================================================
    // 📚 STUDY & TASKS HUB
    // ========================================================

    private void setupStudyHub() {
        subTabTasks.setOnClickListener(v -> switchStudySubTool(0));
        subTabNotes.setOnClickListener(v -> switchStudySubTool(1));
        subTabAnalytics.setOnClickListener(v -> switchStudySubTool(2));

        btnAddTask.setOnClickListener(v -> {
            String title = etNewTask.getText().toString().trim();
            if (title.isEmpty()) return;
            etNewTask.setText("");
            createStudyTask(title);
        });

        btnQuizNotes.setOnClickListener(v -> {
            selectTab(1); // Jump to AI chat
            sendChatMessage("Quiz me on my Thermodynamics study notes");
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

    private void switchStudySubTool(int toolIndex) {
        sectionTasks.setVisibility(toolIndex == 0 ? View.VISIBLE : View.GONE);
        sectionNotes.setVisibility(toolIndex == 1 ? View.VISIBLE : View.GONE);
        sectionAnalytics.setVisibility(toolIndex == 2 ? View.VISIBLE : View.GONE);

        updateSubChipStyle(subTabTasks, toolIndex == 0);
        updateSubChipStyle(subTabNotes, toolIndex == 1);
        updateSubChipStyle(subTabAnalytics, toolIndex == 2);
    }

    private void createStudyTask(String title) {
        String host = getBackendHost();
        String url = host + "/api/tasks?username=" + getActiveUsername();

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
                    addTaskRowLocally(title, false);
                }
            });
        } catch (Exception e) {
            addTaskRowLocally(title, false);
        }
    }

    private void loadRecentTasks() {
        String host = getBackendHost();
        String url = host + "/api/tasks?username=" + getActiveUsername();

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
                    tvMetricsTasks.setText(String.valueOf(response.length()));
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
        params.setMargins(0, 0, 0, 10);
        row.setLayoutParams(params);

        CheckBox cb = new CheckBox(this);
        cb.setChecked(done);
        cb.setText(title);
        cb.setTextColor(0xFF0F172A);
        cb.setTextSize(13);

        row.addView(cb);
        containerTasksList.addView(row, 0);
    }

    // ========================================================
    // ⚙️ SETTINGS & BLE SETUP
    // ========================================================

    private void setupSettingsAndBle() {
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
                tvBleProgress.setText("Scan stopped");
            } else {
                pbScanning.setVisibility(View.VISIBLE);
                tvBleProgress.setText("Searching for DeskMate…");
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
                    Toast.makeText(MainActivity.this, "Desk Lamp " + (isLampOn ? "ON" : "OFF"), Toast.LENGTH_SHORT).show();
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

        quickLamp.setText(isLampOn ? "💡 Lamp: ON" : "💡 Lamp: OFF");
        quickLamp.setBackgroundResource(isLampOn ? R.drawable.chip_active_bg : R.drawable.chip_bg);
        quickLamp.setTextColor(isLampOn ? 0xFFFFFFFF : 0xFF0F172A);
    }

    private void syncDeviceState() {
        String host = getBackendHost();
        tvOledMode.setText("Syncing…");
        String url = host + "/api/snapshot?username=" + getActiveUsername();
        backendClient.getObject(url, new BackendClient.JsonObjectCallback() {
            @Override
            public void onSuccess(JSONObject response) {
                JSONObject dev = response.optJSONObject("device");
                boolean online = dev != null && (dev.optBoolean("online", false)
                        || dev.optBoolean("websocket_connected", false)
                        || dev.optBoolean("wifi_connected", false));

                if (online) {
                    tvOledMode.setText("DeskMate AI: OK");
                    badgeStatus.setText("🟢 Online");
                    badgeStatus.setTextColor(0xFF059669);
                } else {
                    tvOledMode.setText("Offline (Local Active)");
                    badgeStatus.setText("🔵 BLE Mode");
                    badgeStatus.setTextColor(0xFF2563EB);
                }

                // Update real independent metrics for this user
                JSONObject analytics = response.optJSONObject("analytics");
                if (analytics != null) {
                    int focusMins = analytics.optInt("focus_minutes_today", 0);
                    int cycles = analytics.optInt("pomodoro_cycles_today", 0);
                    int openTasks = analytics.optInt("tasks_open", 0);
                    int streak = analytics.optInt("current_streak_days", 0);

                    tvMetricsFocus.setText(focusMins + "m");
                    tvMetricsCycles.setText(String.valueOf(cycles));
                    tvMetricsTasks.setText(String.valueOf(openTasks));
                    tvMetricsStreak.setText(streak + "d");
                }
                Toast.makeText(MainActivity.this, "Synced user data!", Toast.LENGTH_SHORT).show();
            }

            @Override
            public void onError(String error) {
                tvOledMode.setText("Offline (Local Active)");
                badgeStatus.setText("🔵 BLE Mode");
                badgeStatus.setTextColor(0xFF2563EB);
            }
        });
    }

    private String getActiveUsername() {
        return prefs.getString(KEY_USERNAME, "alok17");
    }

    private String getActiveDisplayName() {
        return prefs.getString(KEY_DISPLAY_NAME, "Alok");
    }

    private String getActiveCompetitionCode() {
        return prefs.getString(KEY_COMP_CODE, "ALOK-7572");
    }

    private void setActiveUser(String username, String displayName, String compCode) {
        prefs.edit()
            .putString(KEY_USERNAME, username)
            .putString(KEY_DISPLAY_NAME, displayName)
            .putString(KEY_COMP_CODE, compCode)
            .apply();
        backendClient.setUsername(username);
        updateUserUI();
        loadRecentTasks();
        syncDeviceState();
    }

    private void updateUserUI() {
        if (tvActiveUserInfo != null) {
            tvActiveUserInfo.setText("Logged in as: " + getActiveDisplayName() + " (@" + getActiveUsername() + ")");
        }
        if (tvActiveUserCode != null) {
            tvActiveUserCode.setText("Competition Code: " + getActiveCompetitionCode());
        }
        if (tvCompetitionCode != null) {
            tvCompetitionCode.setText(getActiveCompetitionCode());
        }
    }

    private void showAccountSwitchDialog() {
        String host = getBackendHost();
        Toast.makeText(this, "Fetching registered accounts...", Toast.LENGTH_SHORT).show();
        backendClient.getArray(host + "/api/auth/accounts", new BackendClient.JsonArrayCallback() {
            @Override
            public void onSuccess(JSONArray accounts) {
                if (accounts.length() == 0) {
                    Toast.makeText(MainActivity.this, "No accounts found on server", Toast.LENGTH_SHORT).show();
                    return;
                }
                String[] names = new String[accounts.length()];
                for (int i = 0; i < accounts.length(); i++) {
                    JSONObject acc = accounts.optJSONObject(i);
                    if (acc != null) {
                        String display = acc.optString("display_name", "User");
                        String user = acc.optString("username", "user");
                        String code = acc.optString("competition_code", "");
                        names[i] = display + " (@" + user + ") — " + code;
                    }
                }
                new AlertDialog.Builder(MainActivity.this)
                    .setTitle("Select Active User Account")
                    .setItems(names, (dialog, which) -> {
                        JSONObject selected = accounts.optJSONObject(which);
                        if (selected != null) {
                            String uname = selected.optString("username", "alok17");
                            String dname = selected.optString("display_name", "Alok");
                            String code = selected.optString("competition_code", "ALOK-7572");
                            setActiveUser(uname, dname, code);
                            Toast.makeText(MainActivity.this, "Switched to " + dname + "!", Toast.LENGTH_SHORT).show();
                        }
                    })
                    .setNegativeButton("Cancel", null)
                    .show();
            }

            @Override
            public void onError(String error) {
                Toast.makeText(MainActivity.this, "Could not fetch accounts: " + error, Toast.LENGTH_LONG).show();
            }
        });
    }

    private String getBackendHost() {
        return etBackendHost.getText().toString().trim();
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
        tvBleProgress.setText("Found: " + device.getName());

        containerDiscoveredDevice.setVisibility(View.VISIBLE);
        tvDiscoveredName.setText(device.getName());
        tvDiscoveredMac.setText("MAC: " + device.getAddress() + " | RSSI: " + device.getRssi() + " dBm");
    }

    @Override
    public void onConnectionStateChange(boolean connected, String deviceName) {
        if (connected) {
            badgeStatus.setText("🔵 BLE Connected");
            badgeStatus.setTextColor(0xFF059669);
            tvBleProgress.setText("Connected to " + deviceName);
            layoutWifiForm.setVisibility(View.VISIBLE);
            tvOledStatus.setText("WIFI: Config Pending | BLE: OK");
            Toast.makeText(this, "Paired with " + deviceName + "!", Toast.LENGTH_SHORT).show();
        } else {
            badgeStatus.setText("🔵 BLE Ready");
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
        badgeStatus.setText("🟢 Online (" + assignedIp + ")");
        badgeStatus.setTextColor(0xFF059669);

        String newHost = "http://" + assignedIp + ":8000";
        etBackendHost.setText(newHost);
        prefs.edit().putString(KEY_BACKEND_HOST, newHost).apply();

        new AlertDialog.Builder(this)
                .setTitle("🎉 Wi-Fi Connected!")
                .setMessage("Your DeskMate AI Assistant is now online at IP: " + assignedIp + ".\n\nYou can chat with your assistant and control hardware.")
                .setPositiveButton("Start Chatting", (d, w) -> {
                    closeSettingsPage();
                    selectTab(1);
                })
                .setNegativeButton("OK", (d, w) -> closeSettingsPage())
                .show();
    }

    @Override
    public void onError(String message) {
        pbScanning.setVisibility(View.GONE);
        tvBleProgress.setText(message);
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    // ========================================================
    // 🔒 PERMISSIONS & BLUETOOTH
    // ========================================================

    private void checkBluetoothState(boolean showDialogIfDisabled) {
        if (!bleManager.isBluetoothEnabled()) {
            bannerBluetooth.setVisibility(View.VISIBLE);
            badgeStatus.setText("⚠️ BLE Off");
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
            badgeStatus.setText("🟢 Online");
            badgeStatus.setTextColor(0xFF059669);
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
