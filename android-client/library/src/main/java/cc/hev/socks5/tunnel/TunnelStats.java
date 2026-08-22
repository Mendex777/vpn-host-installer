package cc.hev.socks5.tunnel;

/**
 * Statistics for tunnel data transfer.
 */
public class TunnelStats {
    private final long txBytes;
    private final long rxBytes;
    private final long txPackets;
    private final long rxPackets;
    
    public TunnelStats(long txBytes, long rxBytes, long txPackets, long rxPackets) {
        this.txBytes = txBytes;
        this.rxBytes = rxBytes;
        this.txPackets = txPackets;
        this.rxPackets = rxPackets;
    }
    
    public long getTxBytes() {
        return txBytes;
    }
    
    public long getRxBytes() {
        return rxBytes;
    }
    
    public long getTxPackets() {
        return txPackets;
    }
    
    public long getRxPackets() {
        return rxPackets;
    }
    
    /**
     * Format bytes to human-readable format
     */
    public static String formatBytes(long bytes) {
        if (bytes < 1024) {
            return bytes + " B";
        }
        int exp = (int) (Math.log(bytes) / Math.log(1024));
        String pre = "KMGTPE".charAt(exp - 1) + "iB";
        return String.format("%.2f %s", bytes / Math.pow(1024, exp), pre);
    }
    
    @Override
    public String toString() {
        return String.format("TunnelStats{tx=%s (%d packets), rx=%s (%d packets)}",
                formatBytes(txBytes), txPackets,
                formatBytes(rxBytes), rxPackets);
    }
}
