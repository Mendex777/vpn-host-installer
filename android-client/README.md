# Metadmin Relay for Android

Experimental Android client for the HTTPS short-poll relay. It uses Android `VpnService`, a local SOCKS5 polling transport, and `hev-socks5-tunnel` for TUN-to-SOCKS conversion.

Build with Android Studio or `./gradlew assembleDebug`. Enter the relay HTTPS URL and access key in the app; credentials are not committed to the repository.

This is a prototype: validate stability, battery consumption and DNS/UDP behavior before daily use.
