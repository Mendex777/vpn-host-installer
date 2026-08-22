package cc.hev.socks5.tunnel;

/**
 * Exception thrown when tunnel operations fail.
 */
public class TunnelException extends Exception {
    
    public TunnelException(String message) {
        super(message);
    }
    
    public TunnelException(String message, Throwable cause) {
        super(message, cause);
    }
    
    public TunnelException(Throwable cause) {
        super(cause);
    }
}
