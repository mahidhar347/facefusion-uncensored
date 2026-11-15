import AppKit
import WebKit

final class Launcher: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKDownloadDelegate {
    private let address = URL(string: "http://127.0.0.1:7860")!
    private let directory = Bundle.main.bundleURL.deletingLastPathComponent().standardizedFileURL
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let icon = Bundle.main.url(forResource: "FaceFusion", withExtension: "icns") {
            NSApp.applicationIconImage = NSImage(contentsOf: icon)
        }
        installMenus()
        webView = WKWebView()
        webView.uiDelegate = self
        webView.navigationDelegate = self
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false
        )
        window.title = "FaceFusion"
        window.contentView = webView
        window.setFrameAutosaveName("FaceFusionWindow")
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        reload()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        if server?.isRunning == true { server?.terminate() }
    }

    private func installMenus() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit FaceFusion", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        for (title, action, key) in [("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = edit
        menu.addItem(editItem)

        let viewItem = NSMenuItem()
        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r").target = self
        viewItem.submenu = view
        menu.addItem(viewItem)
        NSApp.mainMenu = menu
    }

    @objc private func reload() {
        webView.loadHTMLString("<body style='font: 17px -apple-system; margin: 3em'>Starting FaceFusion…</body>", baseURL: nil)
        checkServer(remaining: 120, canStart: true)
    }

    private func checkServer(remaining: Int, canStart: Bool) {
        let request = URLRequest(url: address.appendingPathComponent("config"), timeoutInterval: 2)
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let ready = (response as? HTTPURLResponse)?.statusCode == 200 &&
                data.flatMap { String(data: $0, encoding: .utf8) }?.contains("FaceFusion") == true
            DispatchQueue.main.async {
                if ready {
                    self.webView.load(URLRequest(url: self.address))
                } else if remaining == 0 {
                    self.showError("The local engine did not respond. See launcher.log in the FaceFusion folder.")
                } else {
                    if canStart && self.server?.isRunning != true {
                        do { try self.startServer() } catch {
                            self.showError(error.localizedDescription)
                            return
                        }
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                        self.checkServer(remaining: remaining - 1, canStart: false)
                    }
                }
            }
        }.resume()
    }

    private func startServer() throws {
        let logURL = directory.appendingPathComponent("launcher.log")
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        let log = try FileHandle(forWritingTo: logURL)
        try log.seekToEnd()
        let process = Process()
        process.executableURL = directory.appendingPathComponent(".venv/bin/python")
        process.currentDirectoryURL = directory
        process.arguments = ["-u", "facefusion.py", "run"]
        var environment = ProcessInfo.processInfo.environment
        let paths = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        environment["PATH"] = (paths + [environment["PATH"] ?? ""]).joined(separator: ":")
        environment["GRADIO_ANALYTICS_ENABLED"] = "False"
        environment["GRADIO_SERVER_NAME"] = "127.0.0.1"
        environment["GRADIO_SERVER_PORT"] = "7860"
        process.environment = environment
        process.standardOutput = log
        process.standardError = log
        try process.run()
        server = process
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "FaceFusion could not start"
        alert.informativeText = message
        alert.beginSheetModal(for: window)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload {
            decisionHandler(.download)
        } else if action.navigationType == .linkActivated, let url = action.request.url,
                  let scheme = url.scheme, ["http", "https"].contains(scheme), url.host != address.host {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let attachment = (response.response as? HTTPURLResponse)?
            .value(forHTTPHeaderField: "Content-Disposition")?.lowercased().hasPrefix("attachment") == true
        decisionHandler(attachment || !response.canShowMIMEType ? .download : .allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.url : nil)
        }
    }
}

let app = NSApplication.shared
let launcher = Launcher()
app.delegate = launcher
app.setActivationPolicy(.regular)
app.run()
