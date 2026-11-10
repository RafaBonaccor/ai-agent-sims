# Project-local Appium

This directory keeps Appium and its XCUITest driver scoped to this repository; it does not install either package globally. The game-managed server uses this directory's `.appium` folder as `APPIUM_HOME`, so the registered driver stays project-local too.

## Install and run

From the repository root, install dependencies and register the XCUITest driver once:

```sh
npm --prefix tools/appium install
APPIUM_HOME="$PWD/tools/appium/.appium" npm --prefix tools/appium exec -- appium driver install xcuitest
```

In the game, select the **Mobile Automation** agent. Its dashboard shows server health and connected devices, can scan installed iOS apps, open an app selected by the user, and show a near-live screen preview refreshed every 1.5 seconds while the automation session is active. The managed server binds only to `127.0.0.1:4723`; **Stop Appium** stops only a server started by this game. The log is written to `data/appium.log`. You can also start it manually with `APPIUM_HOME="$PWD/tools/appium/.appium" npm --prefix tools/appium run server`.

## iPhone prerequisites

- macOS with the full Xcode application installed and selected with `xcode-select` (Command Line Tools alone are insufficient).
- iPhone connected by USB, unlocked, and trusted by this Mac.
- Developer Mode enabled on iOS 16 and later.
- WebDriverAgent signing/provisioning configured in Xcode for the Apple ID/team used with the phone.

Validate the host setup with:

```sh
APPIUM_HOME="$PWD/tools/appium/.appium" npm --prefix tools/appium exec -- appium driver doctor xcuitest
```

The dashboard's app scan creates a temporary XCUITest session to list apps; launching an app keeps its Appium session open until **End session**. The screen preview uses Appium screenshots rather than a video stream. On first real-device automation, XCUITest/WebDriverAgent may require Developer Mode and signing with a Personal Team in Xcode. This feature only lists and launches apps; it does not publish content or perform account actions.

## Versioning

`package-lock.json` pins the resolved Appium server and driver versions. Keep it in version control so other installs use the same compatible toolchain. Dependencies live in this folder's `node_modules`, not in a global npm location.
