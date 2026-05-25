# Mobile Platform Setup Guide

ScreenForge supports Android and iOS in addition to Web. This guide walks through the full setup for each mobile platform.

## Android Setup

### Prerequisites

1. **ADB (Android Debug Bridge)** — part of Android SDK platform-tools
2. **A connected device or emulator** with USB debugging enabled
3. **Python dependencies** installed

### Step 1: Install Dependencies

```bash
pip install screenforge[android]
# or manually:
pip install uiautomator2 adbutils
```

### Step 2: Connect Device

**Physical device:**
1. Enable Developer Options on your Android phone (Settings → About Phone → tap Build Number 7 times)
2. Enable USB Debugging (Settings → Developer Options → USB Debugging)
3. Connect via USB cable
4. Confirm "Allow USB debugging" prompt on the phone

**Emulator:**
```bash
# Start an emulator (Android Studio must be installed)
emulator -avd Pixel_6_API_34
```

### Step 3: Verify Connection

```bash
adb devices
# Should show:
# List of devices attached
# XXXXXXXX    device
```

### Step 4: Initialize uiautomator2

First-time setup for a new device:

```bash
python -m uiautomator2 init
```

This installs the ATX agent app on the device.

### Step 5: Test with ScreenForge

```bash
# Run doctor to verify everything
screenforge --doctor --platform android

# Try a simple action
screenforge --action goto --platform android --extra-value "https://example.com"

# Inspect the current UI tree
echo '{"operation":"inspect_ui","platform":"android"}' | screenforge --tool-stdin
```

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANDROID_SERIAL` | (auto-detect) | Device serial from `adb devices` |
| `ANDROID_CONNECT_TIMEOUT` | `10.0` | Connection timeout in seconds |

CLI overrides:
```bash
# Connect to a specific device when multiple are connected
screenforge --action click --platform android --device-serial XXXXXXXX \
  --locator-type text --locator-value "Login"
```

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `adb devices` shows "unauthorized" | Unlock phone, tap "Allow USB debugging" |
| `adb devices` shows "offline" | Reconnect USB cable, or run `adb kill-server && adb start-server` |
| uiautomator2 "connection refused" | Run `python -m uiautomator2 init` again |
| Screenshot returns empty | Ensure screen is on and unlocked |

---

## iOS Setup

### Prerequisites

1. **macOS** with Xcode installed (iOS testing requires a Mac)
2. **A connected iPhone/iPad** or iOS Simulator
3. **WebDriverAgent (WDA)** installed on the device
4. **Python dependencies** installed

### Step 1: Install Dependencies

```bash
pip install screenforge[ios]
# or manually:
pip install facebook-wda
```

### Step 2: Install WebDriverAgent

WDA is a test automation framework that runs on the iOS device. You need to compile and install it once.

**Option A: Using tidevice (recommended for physical devices)**

```bash
# Install tidevice
pip install tidevice

# List connected devices
tidevice list

# If WDA is already installed (signed via Xcode previously):
tidevice -u <UDID> wdaproxy -B com.facebook.WebDriverAgentRunner.xctrunner --port 8100
```

**Option B: Using Xcode (first-time setup)**

1. Clone WebDriverAgent:
   ```bash
   git clone https://github.com/appium/WebDriverAgent.git
   cd WebDriverAgent
   ```

2. Open in Xcode:
   ```bash
   open WebDriverAgent.xcodeproj
   ```

3. Configure signing:
   - Select `WebDriverAgentRunner` target
   - Go to Signing & Capabilities
   - Select your Apple Developer Team
   - Change Bundle Identifier to something unique (e.g., `com.yourname.WebDriverAgentRunner`)

4. Build and run on your device:
   - Select your connected device as the target
   - Product → Test (or Cmd+U)
   - Trust the developer certificate on device: Settings → General → VPN & Device Management

5. WDA will start and print a URL like:
   ```
   ServerURLHere->http://192.168.1.xxx:8100<-ServerURLHere
   ```

**Option C: Using Simulator (easiest for testing)**

```bash
# Boot a simulator
xcrun simctl boot "iPhone 16"

# WDA is not needed for basic simctl operations, but for full ScreenForge support:
# Install and run WDA on the simulator via Xcode (same steps as Option B, select simulator as target)
```

### Step 3: Verify WDA Connection

```bash
# Check WDA status (replace URL if WDA is on a different port/host)
curl -s http://localhost:8100/status | python -m json.tool
```

Expected output includes:
```json
{
  "value": {
    "state": "success",
    "os": { "version": "18.x.x" },
    "ready": true
  }
}
```

### Step 4: Test with ScreenForge

```bash
# Run doctor to verify everything
screenforge --doctor --platform ios

# Inspect the current UI tree
echo '{"operation":"inspect_ui","platform":"ios"}' | screenforge --tool-stdin

# Try a simple action
screenforge --action click --platform ios --locator-type text --locator-value "Settings"
```

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `WDA_URL` | `http://localhost:8100` | WebDriverAgent URL |
| `IOS_DEVICE_UDID` | (auto-detect) | Device UDID for recording |

CLI overrides:
```bash
# Connect to WDA on a custom URL
screenforge --action click --platform ios --device-url http://192.168.1.100:8100 \
  --locator-type text --locator-value "Login"

# Specify device UDID
screenforge --doctor --platform ios --device-serial 00008110-XXXXXXXXXXXX
```

### Screen Recording

iOS recording uses `xcrun simctl io recordVideo` (macOS only, works with both simulators and physical devices):

- Automatically detected when running on macOS with Xcode installed
- Falls back gracefully with a clear message on non-macOS systems
- Requires the device UDID (auto-detected from booted simulators, or set `IOS_DEVICE_UDID`)

### Troubleshooting

| Problem | Fix |
|---------|-----|
| "No module named 'wda'" | `pip install screenforge[ios]` or `pip install facebook-wda` |
| "Connection refused" on 8100 | WDA is not running. Start it via tidevice or Xcode |
| Device shows "Offline" in Xcode | Unlock phone, trust the computer, check cable |
| "Could not launch WDA" | Re-sign WDA in Xcode with your developer certificate |
| Screenshots are black | Ensure device screen is on and not in a DRM-protected app |
| Recording says "requires macOS" | iOS recording only works on macOS with Xcode tools |

---

## Multi-Device Testing

When multiple devices are connected, specify which one to use:

```bash
# Android: use device serial
screenforge --action goto --platform android --device-serial emulator-5554 \
  --extra-value "https://example.com"

# iOS: use device URL (each device/WDA instance runs on a different port)
screenforge --action goto --platform ios --device-url http://localhost:8200 \
  --extra-value "https://example.com"
```

Or set environment variables for your default device:

```bash
export ANDROID_SERIAL=emulator-5554
export WDA_URL=http://localhost:8100
export IOS_DEVICE_UDID=00008110-XXXXXXXXXXXX
```

---

## Quick Comparison

| | Android | iOS | Web |
|---|---------|-----|-----|
| **OS required** | Any (Mac/Linux/Windows) | macOS only | Any |
| **Device setup** | USB debug + `u2 init` | Xcode + WDA install | None (uses bundled Chromium) |
| **Connection** | ADB (USB/WiFi) | WDA (HTTP) | CDP (localhost) |
| **Recording** | scrcpy | xcrun simctl | Playwright video API |
| **Time to first test** | ~5 min | ~15 min (first time) | ~1 min |
| **Install command** | `pip install screenforge[android]` | `pip install screenforge[ios]` | `pip install screenforge` (included) |
