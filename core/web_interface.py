# web_interface.py
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
import threading
import webbrowser
from werkzeug.serving import make_server
import time
import requests
import traceback
from path_config import path_config
from game_config import game_config


WEB_DEFAULT_PORT = game_config.int("web.default_port", 5000, min_value=1, max_value=65535)
WEB_BROWSER_OPEN_DELAY_SECONDS = game_config.float("web.browser_open_delay_seconds", 2, min_value=0.0)
WEB_SHUTDOWN_REQUEST_TIMEOUT_SECONDS = game_config.float("web.shutdown_request_timeout_seconds", 2, min_value=0.1)
WEB_SHUTDOWN_JOIN_TIMEOUT_SECONDS = game_config.float("web.shutdown_join_timeout_seconds", 3, min_value=0.1)

class WebInterface:
    def __init__(self, host="127.0.0.1", port=WEB_DEFAULT_PORT, open_browser=True):
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.templates_dir = path_config.templates_dir
        self.static_dir = path_config.static_dir
        self.app = Flask(
            __name__,
            template_folder=str(self.templates_dir),
            static_folder=str(self.static_dir),
        )
        self.game_engine = None
        self.server_thread = None
        self.server = None
        self.running = False

        self._create_directories()
        self._setup_routes()

    def _create_directories(self):
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        static = self.static_dir
        static.mkdir(parents=True, exist_ok=True)
        (static / "css").mkdir(exist_ok=True)
        (static / "js").mkdir(exist_ok=True)

    def _setup_routes(self):
        """Set up Flask routes."""
        @self.app.route("/")
        def index():
            return render_template("index.html")

        @self.app.route("/health")
        def health_check():
            return jsonify({"status": "healthy"})

        @self.app.route("/shutdown")
        def shutdown():
            shutdown_func = request.environ.get("werkzeug.server.shutdown")
            if shutdown_func:
                shutdown_func()
            return jsonify({"status": "shutting down"})

        @self.app.route("/static/<path:filename>")
        def serve_static(filename):
            return send_from_directory(self.static_dir, filename)

        # ==================== API ROUTES ====================
        @self.app.route("/api/game_state")
        def get_game_state():
            if not self.game_engine:
                return jsonify({"error": "Game engine not available"}), 500
            state = self.game_engine.get_game_state()
            if isinstance(state, dict):
                state = dict(state)
                if hasattr(self.game_engine, "get_resume_context"):
                    state["resume_context"] = self.game_engine.get_resume_context()
            return jsonify(state)

        @self.app.route("/api/combat_state")
        def get_combat_state():
            if not self.game_engine:
                return jsonify({"active": False})
            return jsonify(self.game_engine.get_combat_state())

        @self.app.route("/api/combat_map")
        def get_combat_map():
            if not self.game_engine:
                return jsonify({"map_grid": "No active map", "legend": ""})
            return jsonify(self.game_engine.get_combat_map())

        @self.app.route("/api/npcs")
        def get_npcs():
            if not self.game_engine:
                return jsonify([])
            return jsonify(self.game_engine.get_npcs())

        @self.app.route("/api/quests")
        def get_quests():
            if not self.game_engine:
                return jsonify([])
            return jsonify(self.game_engine.get_quests())

        @self.app.route("/api/inventory")
        def get_inventory():
            if not self.game_engine:
                return jsonify([])
            state = self.game_engine.get_game_state()
            inv = state.get("player", {}).get("inventory", [])
            return jsonify(inv)

        @self.app.route("/api/token_usage")
        def get_token_usage():
            if not self.game_engine:
                return jsonify({"total_tokens": 0, "calls": []})
            return jsonify(self.game_engine.get_token_usage())

        @self.app.route("/api/action", methods=["POST"])
        def handle_action():
            if not self.game_engine:
                return jsonify({"error": "Game engine not available"}), 500
            try:
                data = request.get_json() or {}
                result = self.game_engine.process_player_action(data.get("action", ""))
                return jsonify(result)
            except Exception as e:
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500

    def set_game_engine(self, game_engine):
        """Set the game engine reference (called once)."""
        self.game_engine = game_engine
        print("🎮 Game engine connected to web interface")

    def create_templates(self):
        """No longer needed - files are now static"""
        print("📁 Using static HTML/CSS/JS files")
        # You can leave this method empty or remove calls to it

    def start_server(self):
        def run_server():
            self.running = True
            self.server = make_server(self.host, self.port, self.app)
            print(f"🌐 Starting server on http://{self.host}:{self.port}")
            try:
                self.server.serve_forever()
            finally:
                self.running = False

        self.server_thread = threading.Thread(target=run_server, daemon=False)
        self.server_thread.start()

        time.sleep(WEB_BROWSER_OPEN_DELAY_SECONDS)
        if self.open_browser:
            webbrowser.open(f"http://{self.host}:{self.port}")

    def run(self):
        # self.create_templates()
        self.start_server()
        
    def stop_server(self):
        """Stop the Flask server cleanly."""
        if self.server and self.running:
            print("   Stopping Flask server...")
            try:
                # Try graceful shutdown
                try:
                    requests.get(
                        f"http://{self.host}:{self.port}/shutdown",
                        timeout=WEB_SHUTDOWN_REQUEST_TIMEOUT_SECONDS,
                    )
                except:
                    pass
                
                # Force shutdown
                if self.server:
                    self.server.shutdown()
                
                # Wait for thread
                if self.server_thread:
                    self.server_thread.join(timeout=WEB_SHUTDOWN_JOIN_TIMEOUT_SECONDS)
                
                self.running = False
                print("   Web server stopped")
            except Exception as e:
                print(f"   Error during shutdown: {e}")

if __name__ == "__main__":
    class MockEngine:
        def get_game_state(self):
            return {"player": {"identity": {"name": "Aburi"}, "derived": {"HP": 320, "HP_max": 320}}, "world": {"location": {"settlement": "Test Town"}}}
        def process_player_action(self, action):
            return {"narrative": f"You performed: {action}"}
        def get_combat_state(self):
            return {"active": False}
        def get_combat_map(self):
            return {"map_grid": "No active map", "legend": ""}
        def get_npcs(self):
            return []
        def get_quests(self):
            return []

    web = WebInterface()
    web.set_game_engine(MockEngine())
    web.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
