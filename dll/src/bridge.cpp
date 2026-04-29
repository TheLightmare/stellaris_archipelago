#include "bridge.h"
#include "console.h"
#include "logging.h"
#include <windows.h>
#include <thread>
#include <atomic>
#include <string>
#include <sstream>

static const char* PIPE_NAME = "\\\\.\\pipe\\stellaris_archipelago";
static const DWORD PIPE_BUFFER_SIZE = 4096;
static std::thread g_serverThread;
static std::atomic<bool> g_running{false};
static HANDLE g_pipe = INVALID_HANDLE_VALUE;

static void send_response(HANDLE pipe, const std::string& response) {
    std::string msg = response + "\n";
    DWORD written;
    WriteFile(pipe, msg.c_str(), (DWORD)msg.size(), &written, nullptr);
}

static void handle_message(HANDLE pipe, const std::string& message) {
    if (message.empty()) return;
    if (message.rfind("EFFECT ", 0) == 0) {
        console_queue_command("effect " + message.substr(7));
        send_response(pipe, "OK");
    } else if (message.rfind("EVENT ", 0) == 0) {
        console_queue_command("event " + message.substr(6));
        send_response(pipe, "OK");
    } else if (message.rfind("RAW ", 0) == 0) {
        console_queue_command(message.substr(4));
        send_response(pipe, "OK");
    } else if (message.rfind("BATCH ", 0) == 0) {
        std::istringstream stream(message.substr(6));
        std::string cmd; int count = 0;
        while (std::getline(stream, cmd, '|')) { if (!cmd.empty()) { console_queue_command(cmd); count++; } }
        send_response(pipe, "OK BATCH " + std::to_string(count));
    } else if (message == "FLUSH") {
        int flushed = console_process_queue();
        send_response(pipe, "OK FLUSHED " + std::to_string(flushed));
    } else if (message == "PING") {
        send_response(pipe, console_is_ready() ? "PONG READY" : "PONG NOT_READY");
    } else if (message == "STATUS") {
        send_response(pipe, console_is_ready() ? "STATUS CONSOLE_READY" : "STATUS CONSOLE_NOT_FOUND");
    } else {
        ap_log("Bridge: unknown message: %s", message.c_str());
        send_response(pipe, "ERROR unknown command");
    }
}

static void server_loop() {
    ap_log("Bridge: starting pipe server on %s", PIPE_NAME);
    while (g_running) {
        g_pipe = CreateNamedPipeA(PIPE_NAME, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1, PIPE_BUFFER_SIZE, PIPE_BUFFER_SIZE, 1000, nullptr);
        if (g_pipe == INVALID_HANDLE_VALUE) { ap_log("Bridge: CreateNamedPipe failed (%d)", GetLastError()); Sleep(1000); continue; }
        ap_log("Bridge: waiting for client connection...");
        BOOL connected = ConnectNamedPipe(g_pipe, nullptr);
        if (!connected && GetLastError() != ERROR_PIPE_CONNECTED) {
            if (!g_running) break;
            ap_log("Bridge: ConnectNamedPipe failed (%d)", GetLastError());
            CloseHandle(g_pipe); g_pipe = INVALID_HANDLE_VALUE; continue;
        }
        ap_log("Bridge: client connected!");
        char buffer[PIPE_BUFFER_SIZE]; std::string partial;
        while (g_running) {
            DWORD bytesRead;
            BOOL success = ReadFile(g_pipe, buffer, sizeof(buffer)-1, &bytesRead, nullptr);
            if (!success || bytesRead == 0) {
                DWORD err = GetLastError();
                if (err == ERROR_BROKEN_PIPE || err == ERROR_PIPE_NOT_CONNECTED) ap_log("Bridge: client disconnected");
                else if (g_running) ap_log("Bridge: read error %d", err);
                break;
            }
            buffer[bytesRead] = '\0'; partial += buffer;
            size_t pos;
            while ((pos = partial.find('\n')) != std::string::npos) {
                std::string line = partial.substr(0, pos);
                partial = partial.substr(pos + 1);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                if (!line.empty()) handle_message(g_pipe, line);
            }
        }
        DisconnectNamedPipe(g_pipe); CloseHandle(g_pipe); g_pipe = INVALID_HANDLE_VALUE;
        int flushed = console_process_queue();
        if (flushed > 0) ap_log("Bridge: flushed %d command(s) after client session", flushed);
        if (g_running) { ap_log("Bridge: ready for next client"); }
    }
    ap_log("Bridge: server thread exiting");
}

bool bridge_start() { if (g_running) return true; g_running = true; g_serverThread = std::thread(server_loop); return true; }
void bridge_stop() {
    g_running = false;
    HANDLE dummy = CreateFileA(PIPE_NAME, GENERIC_READ|GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (dummy != INVALID_HANDLE_VALUE) CloseHandle(dummy);
    if (g_serverThread.joinable()) g_serverThread.join();
    if (g_pipe != INVALID_HANDLE_VALUE) { CloseHandle(g_pipe); g_pipe = INVALID_HANDLE_VALUE; }
    ap_log("Bridge: stopped");
}
int bridge_tick() { return console_process_queue(); }
