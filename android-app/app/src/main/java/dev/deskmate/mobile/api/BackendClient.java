package dev.deskmate.mobile.api;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BackendClient {

    public interface JsonObjectCallback {
        void onSuccess(JSONObject response);
        void onError(String error);
    }

    public interface JsonArrayCallback {
        void onSuccess(JSONArray response);
        void onError(String error);
    }

    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private String authToken = null;
    private String userId = null;
    private String username = "alok17";

    public void setAuthToken(String token) {
        this.authToken = token;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getUsername() {
        return username != null ? username : "alok17";
    }

    public void getObject(String urlString, JsonObjectCallback callback) {
        executor.execute(() -> {
            try {
                String body = executeRequest(urlString, "GET", null);
                JSONObject json = new JSONObject(body.isEmpty() ? "{}" : body);
                mainHandler.post(() -> callback.onSuccess(json));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
    }

    public void getArray(String urlString, JsonArrayCallback callback) {
        executor.execute(() -> {
            try {
                String body = executeRequest(urlString, "GET", null);
                JSONArray json = new JSONArray(body.isEmpty() ? "[]" : body);
                mainHandler.post(() -> callback.onSuccess(json));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
    }

    public void post(String urlString, JSONObject payload, JsonObjectCallback callback) {
        executor.execute(() -> {
            try {
                String body = executeRequest(urlString, "POST", payload != null ? payload.toString() : null);
                JSONObject json = new JSONObject(body.isEmpty() ? "{}" : body);
                mainHandler.post(() -> callback.onSuccess(json));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
    }

    public void patch(String urlString, JSONObject payload, JsonObjectCallback callback) {
        executor.execute(() -> {
            try {
                String body = executeRequest(urlString, "PATCH", payload != null ? payload.toString() : null);
                JSONObject json = new JSONObject(body.isEmpty() ? "{}" : body);
                mainHandler.post(() -> callback.onSuccess(json));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
    }

    private String executeRequest(String urlString, String method, String payload) throws Exception {
        URL url = new URL(urlString);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(7000);
        conn.setRequestProperty("Accept", "application/json");

        if (authToken != null && !authToken.isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + authToken);
        }
        if (userId != null && !userId.isEmpty()) {
            conn.setRequestProperty("X-User-Id", userId);
        }
        if (username != null && !username.isEmpty()) {
            conn.setRequestProperty("X-Username", username);
        }

        if (payload != null && (method.equals("POST") || method.equals("PATCH") || method.equals("PUT"))) {
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            try (OutputStream os = conn.getOutputStream()) {
                os.write(payload.getBytes(StandardCharsets.UTF_8));
            }
        }

        int code = conn.getResponseCode();
        InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
        String body = readStream(is);
        conn.disconnect();

        if (code >= 200 && code < 300) {
            return body;
        } else {
            throw new Exception("HTTP " + code + (body.isEmpty() ? "" : ": " + body));
        }
    }

    private String readStream(InputStream is) {
        if (is == null) return "";
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append('\n');
            }
            return sb.toString().trim();
        } catch (Exception e) {
            return "";
        }
    }
}
