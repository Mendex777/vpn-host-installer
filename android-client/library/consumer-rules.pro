# Consumer ProGuard rules for library users

# Keep all native methods
-keepclasseswithmembernames class * {
    native <methods>;
}

# Keep all tunnel classes and their members
-keep class cc.hev.socks5.tunnel.** { *; }
-keepclassmembers class cc.hev.socks5.tunnel.** { *; }
