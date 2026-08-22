# Metadmin Relay for Android

Android `VpnService` client for the multiplexed HTTPS polling relay.

The app establishes a TUN interface, uses `hev-socks5-tunnel` to convert TCP
traffic to a local SOCKS5 server, answers DNS through HEV mapped DNS, and carries
all downstream sessions through one `/mux/down` request. Arbitrary UDP is not
supported.

Build:

```bash
./gradlew assembleDebug
```

The CI workflow downloads and compiles the native HEV library before Gradle.
Enter the public relay HTTPS URL and public token in the app. Credentials are
stored in Android private preferences and are not embedded in the repository.
