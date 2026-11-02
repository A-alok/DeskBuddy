package dev.deskmate.mobile.api;

import android.os.Handler;
import android.os.Looper;

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

    public interface ApiCallback {
        void onSuccess(JSONObject response);
        void onError(String error);
    }

    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public void get(String urlString, ApiCallback callback) {
        executor.execute(() -> {
            try {
                URL url = new URL(urlString);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setRequestProperty("Accept", "application/json");

                int code = conn.getResponseCode();
                InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
                String body = readStream(is);
                conn.disconnect();

                if (code >= 200 && code < 300) {
                    JSONObject json = new JSONObject(body.isEmpty() ? "{}" : body);
                    mainHandler.post(() -> callback.onSuccess(json));
                } else {
                    mainHandler.post(() -> callback.onError("HTTP " + code + ": " + body));
                }
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
    }

    public void post(String urlString, JSONObject payload, ApiCallback callback) {
        executor.execute(() -> {
            try {
                URL url = new URL(urlString);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");

                if (payload != null) {
                    byte[] out = payload.toString().getBytes(StandardCharsets.UTF_8);
                    try (OutputStream os = conn.getOutputStream()) {
                        os.write(out);
                    }
                }

                int code = conn.getResponseCode();
                InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
                String body = readStream(is);
                conn.disconnect();

                if (code >= 200 && code < 300) {
                    JSONObject json = new JSONObject(body.isEmpty() ? "{}" : body);
                    mainHandler.post(() -> callback.onSuccess(json));
                } else {
                    mainHandler.post(() -> callback.onError("HTTP " + code + ": " + body));
                }
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        });
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
