package cc.hev.socks5.tunnel;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.List;

/**
 * Configuration for the HevSocks5Tunnel.
 * Use Builder pattern to construct configuration.
 */
public class TunnelConfig {
    private final String socks5Address;
    private final int socks5Port;
    private final String socks5Username;
    private final String socks5Password;
    private final String tunName;
    private final int tunMtu;
    private final String tunIPv4Address;
    private final String tunIPv4Gateway;
    private final String tunIPv6Address;
    private final String tunIPv6Gateway;
    private final List<String> dnsServers;
    private final int multiQueue;
    
    private TunnelConfig(Builder builder) {
        this.socks5Address = builder.socks5Address;
        this.socks5Port = builder.socks5Port;
        this.socks5Username = builder.socks5Username;
        this.socks5Password = builder.socks5Password;
        this.tunName = builder.tunName;
        this.tunMtu = builder.tunMtu;
        this.tunIPv4Address = builder.tunIPv4Address;
        this.tunIPv4Gateway = builder.tunIPv4Gateway;
        this.tunIPv6Address = builder.tunIPv6Address;
        this.tunIPv6Gateway = builder.tunIPv6Gateway;
        this.dnsServers = builder.dnsServers;
        this.multiQueue = builder.multiQueue;
    }
    
    /**
     * Convert configuration to YAML format for hev-socks5-tunnel
     */
    public String toYaml() {
        StringBuilder yaml = new StringBuilder();
        
        // Main tunnel section
        yaml.append("tunnel:\n");
        yaml.append("  name: ").append(tunName != null ? tunName : "tun0").append("\n");
        yaml.append("  mtu: ").append(tunMtu).append("\n");
        yaml.append("  multi-queue: ").append(multiQueue).append("\n");
        
        if (tunIPv4Address != null && !tunIPv4Address.isEmpty()) {
            yaml.append("  ipv4:\n");
            yaml.append("    address: ").append(tunIPv4Address).append("\n");
            if (tunIPv4Gateway != null && !tunIPv4Gateway.isEmpty()) {
                yaml.append("    gateway: ").append(tunIPv4Gateway).append("\n");
            }
        }
        
        if (tunIPv6Address != null && !tunIPv6Address.isEmpty()) {
            yaml.append("  ipv6:\n");
            yaml.append("    address: ").append(tunIPv6Address).append("\n");
            if (tunIPv6Gateway != null && !tunIPv6Gateway.isEmpty()) {
                yaml.append("    gateway: ").append(tunIPv6Gateway).append("\n");
            }
        }
        
        // SOCKS5 section
        yaml.append("socks5:\n");
        yaml.append("  address: ").append(socks5Address).append("\n");
        yaml.append("  port: ").append(socks5Port).append("\n");
        
        if (socks5Username != null && !socks5Username.isEmpty()) {
            yaml.append("  username: ").append(socks5Username).append("\n");
        }
        
        if (socks5Password != null && !socks5Password.isEmpty()) {
            yaml.append("  password: ").append(socks5Password).append("\n");
        }
        
        // DNS section
        if (dnsServers != null && !dnsServers.isEmpty()) {
            yaml.append("misc:\n");
            yaml.append("  dns:\n");
            for (String dns : dnsServers) {
                yaml.append("    - ").append(dns).append("\n");
            }
        }
        
        return yaml.toString();
    }
    
    public static class Builder {
        private String socks5Address = "127.0.0.1";
        private int socks5Port = 1080;
        private String socks5Username;
        private String socks5Password;
        private String tunName = "tun0";
        private int tunMtu = 8500;
        private String tunIPv4Address = "10.0.0.2";
        private String tunIPv4Gateway = "10.0.0.1";
        private String tunIPv6Address = "fc00::2";
        private String tunIPv6Gateway = "fc00::1";
        private List<String> dnsServers = new ArrayList<>();
        private int multiQueue = 4;
        
        public Builder() {
            // Default DNS servers
            dnsServers.add("8.8.8.8");
            dnsServers.add("8.8.4.4");
        }
        
        public Builder setSocks5Address(@NonNull String address) {
            this.socks5Address = address;
            return this;
        }
        
        public Builder setSocks5Port(int port) {
            if (port <= 0 || port > 65535) {
                throw new IllegalArgumentException("Invalid port: " + port);
            }
            this.socks5Port = port;
            return this;
        }
        
        public Builder setSocks5Username(@Nullable String username) {
            this.socks5Username = username;
            return this;
        }
        
        public Builder setSocks5Password(@Nullable String password) {
            this.socks5Password = password;
            return this;
        }
        
        public Builder setTunName(@NonNull String name) {
            this.tunName = name;
            return this;
        }
        
        public Builder setTunMtu(int mtu) {
            if (mtu < 1280 || mtu > 65535) {
                throw new IllegalArgumentException("Invalid MTU: " + mtu);
            }
            this.tunMtu = mtu;
            return this;
        }
        
        public Builder setTunIPv4Address(@Nullable String address) {
            this.tunIPv4Address = address;
            return this;
        }
        
        public Builder setTunIPv4Gateway(@Nullable String gateway) {
            this.tunIPv4Gateway = gateway;
            return this;
        }
        
        public Builder setTunIPv6Address(@Nullable String address) {
            this.tunIPv6Address = address;
            return this;
        }
        
        public Builder setTunIPv6Gateway(@Nullable String gateway) {
            this.tunIPv6Gateway = gateway;
            return this;
        }
        
        public Builder setDnsServers(@NonNull List<String> servers) {
            this.dnsServers = new ArrayList<>(servers);
            return this;
        }
        
        public Builder addDnsServer(@NonNull String server) {
            this.dnsServers.add(server);
            return this;
        }
        
        public Builder setMultiQueue(int queues) {
            if (queues <= 0) {
                throw new IllegalArgumentException("Invalid multi-queue value: " + queues);
            }
            this.multiQueue = queues;
            return this;
        }
        
        public TunnelConfig build() {
            if (socks5Address == null || socks5Address.isEmpty()) {
                throw new IllegalStateException("SOCKS5 address is required");
            }
            return new TunnelConfig(this);
        }
    }
}
