package cc.hev.socks5.tunnel;

import android.util.Log;
import java.io.FileDescriptor;

public class HevSocks5Tunnel {
    private static final String TAG = "HevSocks5Tunnel";
    private static final String LIBRARY_NAME = "hev-socks5-tunnel-jni";
    private static boolean libraryLoaded = false;
    private static Throwable libraryLoadError = null;
    
    private volatile boolean running = false;
    private Thread tunnelThread = null;
    
    static {
        try {
            System.loadLibrary(LIBRARY_NAME);
            libraryLoaded = true;
            Log.i(TAG, "Native library loaded successfully: " + LIBRARY_NAME);
        } catch (UnsatisfiedLinkError e) {
            libraryLoaded = false;
            libraryLoadError = e;
            Log.e(TAG, "Failed to load native library: " + LIBRARY_NAME, e);
        }
    }
    
    public static boolean isLibraryLoaded() {
        return libraryLoaded;
    }
    
    public static Throwable getLibraryLoadError() {
        return libraryLoadError;
    }
    
    public HevSocks5Tunnel() {
        if (!libraryLoaded) {
            throw new RuntimeException("Native library not loaded", libraryLoadError);
        }
    }
    
    public void startAsync(String configPath, FileDescriptor tunFd) throws TunnelException {
        if (running) {
            throw new TunnelException("Tunnel is already running");
        }
        
        if (configPath == null || configPath.isEmpty()) {
            throw new TunnelException("Config path cannot be null or empty");
        }
        
        if (tunFd == null) {
            throw new TunnelException("TUN file descriptor cannot be null");
        }
        
        int fd = getFdFromFileDescriptor(tunFd);
        if (fd < 0) {
            throw new TunnelException("Invalid TUN file descriptor: " + fd);
        }
        
        running = true;
        final String finalConfigPath = configPath;
        final int finalFd = fd;
        
        tunnelThread = new Thread(() -> {
            try {
                Log.i(TAG, "Starting tunnel thread with config: " + finalConfigPath);
                int result = nativeStart(finalConfigPath, finalFd);
                if (result != 0) {
                    Log.e(TAG, "Tunnel failed with error code: " + result);
                } else {
                    Log.i(TAG, "Tunnel stopped normally");
                }
            } catch (Exception e) {
                Log.e(TAG, "Tunnel thread exception", e);
            } finally {
                running = false;
            }
        }, "HevSocks5Tunnel");
        
        tunnelThread.start();
        
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            // Ignore
        }
        
        if (!running) {
            throw new TunnelException("Tunnel failed to start");
        }
    }
    
    public void startAsync(TunnelConfig config, FileDescriptor tunFd) throws TunnelException {
        if (running) {
            throw new TunnelException("Tunnel is already running");
        }
        
        if (config == null) {
            throw new TunnelException("Config cannot be null");
        }
        
        if (tunFd == null) {
            throw new TunnelException("TUN file descriptor cannot be null");
        }
        
        int fd = getFdFromFileDescriptor(tunFd);
        if (fd < 0) {
            throw new TunnelException("Invalid TUN file descriptor: " + fd);
        }
        
        String configYaml = config.toYaml();
        Log.d(TAG, "Generated config YAML:\n" + configYaml);
        
        running = true;
        final String finalConfigYaml = configYaml;
        final int finalFd = fd;
        
        tunnelThread = new Thread(() -> {
            try {
                Log.i(TAG, "Starting tunnel thread with inline config");
                int result = nativeStartFromString(finalConfigYaml, finalFd);
                if (result != 0) {
                    Log.e(TAG, "Tunnel failed with error code: " + result);
                } else {
                    Log.i(TAG, "Tunnel stopped normally");
                }
            } catch (Exception e) {
                Log.e(TAG, "Tunnel thread exception", e);
            } finally {
                running = false;
            }
        }, "HevSocks5Tunnel");
        
        tunnelThread.start();
        
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            // Ignore
        }
        
        if (!running) {
            throw new TunnelException("Tunnel failed to start");
        }
    }
    
    public void stop() {
        if (!running) {
            Log.w(TAG, "Tunnel is not running");
            return;
        }
        
        Log.i(TAG, "Stopping tunnel");
        nativeStop();
        
        if (tunnelThread != null) {
            try {
                tunnelThread.join(5000);
                if (tunnelThread.isAlive()) {
                    Log.w(TAG, "Tunnel thread did not stop in time");
                    tunnelThread.interrupt();
                }
            } catch (InterruptedException e) {
                Log.e(TAG, "Interrupted while waiting for tunnel thread", e);
            }
            tunnelThread = null;
        }
        
        running = false;
        Log.i(TAG, "Tunnel stopped");
    }
    
    public boolean isRunning() {
        return running;
    }
    
    public TunnelStats getStats() {
        if (!running) {
            return new TunnelStats(0, 0, 0, 0);
        }
        
        long[] stats = nativeGetStats();
        if (stats == null || stats.length != 4) {
            return new TunnelStats(0, 0, 0, 0);
        }
        
        return new TunnelStats(stats[0], stats[1], stats[2], stats[3]);
    }
    
    private native int getFdFromFileDescriptor(FileDescriptor fd);
    private native int nativeStart(String configPath, int tunFd);
    private native int nativeStartFromString(String configYaml, int tunFd);
    private native void nativeStop();
    private native long[] nativeGetStats();
}
