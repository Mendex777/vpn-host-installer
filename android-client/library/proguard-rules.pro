# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# Keep all native methods
-keepclasseswithmembernames class * {
    native <methods>;
}

# Keep all tunnel classes and their members
-keep class cc.hev.socks5.tunnel.** { *; }
-keepclassmembers class cc.hev.socks5.tunnel.** { *; }

# Keep exceptions
-keep public class * extends java.lang.Exception

# Keep FileDescriptor
-keep class java.io.FileDescriptor { *; }
