package cc.hev.socks5.tunnel;

import android.util.Log;

public class HevSocks5Tunnel {
    private static final String TAG = "HevSocks5Tunnel";
    private static boolean loaded;
    private volatile boolean running;
    static { try { System.loadLibrary("hev-socks5-tunnel-jni"); loaded=true; Log.i(TAG,"Native libraries loaded"); } catch(Throwable e){ Log.e(TAG,"Native library load failed",e); } }
    public HevSocks5Tunnel(){if(!loaded)throw new IllegalStateException("Native library not loaded");}
    public void startAsync(String path,int fd)throws TunnelException{if(running)throw new TunnelException("Tunnel already running");if(path==null||path.isEmpty()||fd<0)throw new TunnelException("Invalid tunnel arguments");TProxyStartService(path,fd);running=true;}
    public void stop(){if(running)TProxyStopService();running=false;}
    public boolean isRunning(){return running;}
    public TunnelStats getStats(){long[] s=running?TProxyGetStats():null;return s!=null&&s.length==4?new TunnelStats(s[0],s[1],s[2],s[3]):new TunnelStats(0,0,0,0);}
    private native void TProxyStartService(String path,int fd);
    private native void TProxyStopService();
    private native long[] TProxyGetStats();
}
