package ru.metadmin.relay;

import android.app.*;
import android.content.*;
import android.net.VpnService;
import android.os.*;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import androidx.core.app.NotificationCompat;
import cc.hev.socks5.tunnel.*;

public class RelayVpnService extends VpnService {
    static final String START="ru.metadmin.relay.START", STOP="ru.metadmin.relay.STOP";
    private ParcelFileDescriptor tun; private HevSocks5Tunnel hev; private PollSocksServer socks;
    @Override public void onCreate(){super.onCreate();if(Build.VERSION.SDK_INT>=26)((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(new NotificationChannel("relay","VPN",NotificationManager.IMPORTANCE_LOW));}
    @Override public int onStartCommand(Intent i,int flags,int id){if(i!=null&&STOP.equals(i.getAction()))stopAll();else if(i!=null&&START.equals(i.getAction()))startAll();return START_STICKY;}
    private void startAll(){if(tun!=null)return;startForeground(10,new NotificationCompat.Builder(this,"relay").setSmallIcon(android.R.drawable.stat_sys_warning).setContentTitle("Metadmin Relay").setContentText("VPN подключён").setOngoing(true).build());try{
        android.content.SharedPreferences p=getSharedPreferences("relay",MODE_PRIVATE);socks=new PollSocksServer(p.getString("url",""),p.getString("key",""));socks.start();
        Builder b=new Builder().setSession("Metadmin Relay").setMtu(1500).addAddress("10.77.0.2",24).addRoute("0.0.0.0",0).addDnsServer("1.1.1.1");
        b.addDisallowedApplication(getPackageName());tun=b.establish();if(tun==null)throw new Exception("VPN permission missing");
        hev=new HevSocks5Tunnel();TunnelConfig cfg=new TunnelConfig.Builder().setSocks5Address("127.0.0.1").setSocks5Port(10809).setTunMtu(1500).setTunIPv4Address("10.77.0.2").setTunIPv4Gateway("10.77.0.1").build();
        File configFile=new File(getCacheDir(),"hev.yml");try(FileOutputStream out=new FileOutputStream(configFile)){out.write(cfg.toYaml().getBytes(StandardCharsets.UTF_8));}
        hev.startAsync(configFile.getAbsolutePath(),tun.getFd());
    }catch(Exception e){e.printStackTrace();stopAll();}}
    private void stopAll(){if(hev!=null){try{hev.stop();}catch(Exception ignored){}hev=null;}if(socks!=null){socks.stop();socks=null;}if(tun!=null){try{tun.close();}catch(Exception ignored){}tun=null;}stopForeground(true);stopSelf();}
    @Override public void onDestroy(){stopAll();super.onDestroy();}
    @Override public void onRevoke(){stopAll();super.onRevoke();}
}
