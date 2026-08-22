package ru.metadmin.relay;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.regex.*;

final class PollSocksServer {
    private static final Semaphore DOWNLOAD_SLOTS = new Semaphore(2, true);
    private final String relay, key;
    private final ExecutorService pool=Executors.newCachedThreadPool();
    private volatile boolean running;
    private ServerSocket server;
    PollSocksServer(String relay,String key){this.relay=relay;this.key=key;}
    void start() throws IOException { server=new ServerSocket(); server.setReuseAddress(true); server.bind(new InetSocketAddress("127.0.0.1",10809)); running=true; pool.execute(this::accept); }
    void stop(){running=false;try{server.close();}catch(Exception ignored){}pool.shutdownNow();}
    private void accept(){while(running)try{Socket s=server.accept();pool.execute(()->handle(s));}catch(IOException e){if(running)e.printStackTrace();}}
    private byte[] exact(InputStream in,int n)throws IOException{byte[] b=new byte[n];int p=0,r;while(p<n&&(r=in.read(b,p,n-p))>0)p+=r;if(p!=n)throw new EOFException();return b;}
    private int u(byte b){return b&255;}
    private void handle(Socket sock){String sid=null;try(Socket s=sock){s.setTcpNoDelay(true);InputStream in=s.getInputStream();OutputStream out=s.getOutputStream();
        if(u(exact(in,1)[0])!=5)return;int nm=u(exact(in,1)[0]);exact(in,nm);out.write(new byte[]{5,0});out.flush();
        byte[] h=exact(in,4);if(u(h[0])!=5||u(h[1])!=1)return;String host;int atyp=u(h[3]);
        if(atyp==1)host=InetAddress.getByAddress(exact(in,4)).getHostAddress();else if(atyp==3)host=new String(exact(in,u(exact(in,1)[0])),StandardCharsets.UTF_8);else if(atyp==4)host=InetAddress.getByAddress(exact(in,16)).getHostAddress();else return;
        byte[] pb=exact(in,2);int port=(u(pb[0])<<8)|u(pb[1]);String json="{\"host\":\""+host.replace("\\","\\\\").replace("\"","\\\"")+"\",\"port\":"+port+"}";
        byte[] opened=request("POST","/open",json.getBytes(StandardCharsets.UTF_8),40000);Matcher m=Pattern.compile("\"session\"\\s*:\\s*\"([^\"]+)\"").matcher(new String(opened,StandardCharsets.UTF_8));if(!m.find())throw new IOException("No session");sid=m.group(1);
        out.write(new byte[]{5,0,0,1,0,0,0,0,0,0});out.flush();final String id=sid;final boolean[] live={true};
        Future<?> down=pool.submit(()->{try{while(live[0]){DOWNLOAD_SLOTS.acquire();try{byte[] b=request("GET","/down/"+id+"?wait=1&max=1048576",null,10000);if(b.length>0){synchronized(out){out.write(b);out.flush();}}}finally{DOWNLOAD_SLOTS.release();}}}catch(Exception ignored){}finally{live[0]=false;try{s.shutdownInput();}catch(Exception ignored){}}});
        byte[] b=new byte[262144];int n;while(live[0]&&(n=in.read(b))>0){byte[] chunk=new byte[n];System.arraycopy(b,0,chunk,0,n);request("POST","/up/"+id,chunk,40000);}live[0]=false;down.cancel(true);
    }catch(Exception e){e.printStackTrace();}finally{if(sid!=null)try{request("DELETE","/close/"+sid,null,5000);}catch(Exception ignored){}}}
    private byte[] request(String method,String path,byte[] body,int timeout)throws IOException{HttpURLConnection c=(HttpURLConnection)new URL(relay+path).openConnection();c.setRequestMethod(method);c.setConnectTimeout(10000);c.setReadTimeout(timeout);c.setRequestProperty("X-Relay-Key",key);c.setRequestProperty("Content-Type","application/octet-stream");c.setUseCaches(false);if(body!=null){c.setDoOutput(true);try(OutputStream o=c.getOutputStream()){o.write(body);}}
        int code=c.getResponseCode();if(code==204)return new byte[0];if(code<200||code>=300)throw new IOException("Relay HTTP "+code);try(InputStream i=c.getInputStream();ByteArrayOutputStream o=new ByteArrayOutputStream()){byte[] b=new byte[65536];int n;while((n=i.read(b))>=0)o.write(b,0,n);return o.toByteArray();}finally{c.disconnect();}}
}
