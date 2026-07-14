import os
import sys
import time
import random

# --- CONFIGURATION IMPORT & INITIALIZATION ---
try:
    import config
    import pandas as pd
    from flask import Flask, Response, request, jsonify
    from google.cloud import tasks_v2  # Handled automatically via requirements.txt

    app = Flask(__name__)

except Exception as boot_err:
    print(f"CRITICAL BOOT ERROR DURING INITIALIZATION: {str(boot_err)}", file=sys.stderr)
    sys.exit(1)

# --- CLOUD TASKS ROUTING CONFIGURATION ---
PROJECT_ID = "gen-lang-client-0308183579"
REGION = "europe-west1"
QUEUE_ID = "price-update-queue"


def get_dynamic_tickers():
    try:
        df = pd.read_excel(config.WATCHLIST_PATH)
        return df['Ticker'].dropna().astype(str).str.strip().tolist() if 'Ticker' in df.columns else ["NAS.OL"]
    except Exception as e:
        print(f"Watchlist Read Warning: {e}")
        return ["NAS.OL"]


def run_pipeline_logic(log_func):
    """Encapsulated core pipeline execution logic so both the
    live UI stream and the background worker can utilize it."""
    try:
        import ta_analyzer
        import dashboard_generator
        import sparkline_generator
        import htmlgraph_generator
        import price_fetcherv2 as price_fetcher
    except Exception as import_err:
        log_func(f"Module Import Error: {str(import_err)}")
        return False

    log_func("System Health Check: Verifying Storage Mount Permissions...")

    if config.IS_CLOUD:
        mount_ready = False
        for attempt in range(1, 6):
            try:
                with open(config.WATCHLIST_PATH, "rb") as f:
                    pass
                log_func("[OK] Cloud Storage Mount Verified. Access granted.")
                mount_ready = True
                break
            except Exception:
                log_func(f"[WAIT] Synchronizing bucket storage... (Attempt {attempt}/5)")
                time.sleep(3)

        if not mount_ready:
            log_func("[FATAL] Cloud Storage Timeout. Pipeline aborted. Mount unreadable.")
            return False

    # STAGE 1: Download & Append Price Action Safely
    log_func("Stage 1: Safe Price Action Append Sync")
    tickers = get_dynamic_tickers()
    for t in tickers:
        for line in price_fetcher.update_ticker_data(t):
            log_func(line)
        time.sleep(random.uniform(2, 5))

    # STAGE 2: Quantitative Technical Screener
    log_func("Stage 2: Quantitative Technical Screener")
    for ta_line in ta_analyzer.main():
        log_func(ta_line)

    # STAGE 3: Build Refactored HTML Visual Matrix Screen
    log_func("Stage 3: Building Standalone Dashboard Layout")

    log_func("[Visuals] Generating Sparkline Graphics...")
    try:
        sparkline_generator.process_technical_watchlist()
        log_func("[Visuals] Sparklines rendered successfully.")
    except Exception as spark_err:
        log_func(f"[Visuals] Sparkline Generator Fault: {str(spark_err)}")

    log_func("[Visuals] Generating Technical Price Graphs Graphics...")
    try:
        htmlgraph_generator.compile_visual_dashboard()
        log_func("[Visuals] Price Graph rendered successfully.")
    except Exception as graph_err:
        log_func(f"[Visuals] Graph Generator Fault: {str(graph_err)}")

    try:
        success = dashboard_generator.generate_dashboard(
            excel_path=config.TECHNICAL_FILE,
            output_path=config.DASHBOARD_FILE
        )
        if success:
            log_func("[Dashboard] Success: matrix_dashboard.html recompiled safely.")
        else:
            log_func("[Dashboard] Error: Generation script completed with an execution fault.")
    except Exception as err:
        log_func(f"[Dashboard] Generation Failed Critical Error: {str(err)}")

    return True


@app.route('/')
def load_saved_dashboard():
    if not os.path.exists(config.DASHBOARD_FILE):
        return f"""<body style="background:#0b0c10;color:#f44336;font-family:sans-serif;padding:40px;">
                   <h2>Dashboard Matrix File Offline</h2>
                   <p>The file <code>matrix_dashboard.html</code> has not been generated in cloud storage yet.</p>
                   <p>Run the <a href="/update-prices" style="color:#66fcf1;">Pipeline Sync</a> to generate it now.</p>
                   </body>"""
    with open(config.DASHBOARD_FILE, "r", encoding="utf-8") as f:
        return f.read()


@app.route('/update-prices', methods=['GET', 'POST'])
def update_prices_route():
    # POST requests come from Cloud Scheduler
    if request.method == 'POST':
        try:
            # Force the clear, secure production URL explicitly to bypass internal http proxy redirects
            production_worker_url = "https://olaiprojectv4-90985564727.europe-north1.run.app/execute-worker"

            client = tasks_v2.CloudTasksClient()
            parent = client.queue_path(PROJECT_ID, REGION, QUEUE_ID)

            task = {
                'http_request': {
                    'http_method': tasks_v2.HttpMethod.POST,
                    'url': production_worker_url,
                }
            }

            client.create_task(request={"parent": parent, "task": task})
            return jsonify(
                {"status": "Success", "message": f"Task successfully queued for {production_worker_url}"}), 202

        except Exception as e:
            print(f"Failed to enqueue task: {str(e)}", file=sys.stderr)
            return jsonify({"status": "Error", "message": str(e)}), 500

    # GET requests come from manual browser visits
    return """
    <!DOCTYPE html>
    <html><head><title>Oslo Børs Live Console</title><style>
    body { font-family: monospace; background: #0f172a; color: #e2e8f0; margin: 40px; }
    #console { background: #020617; border: 1px solid #334155; padding: 20px; height: 500px; overflow-y: auto; }
    </style></head><body>
    <h1>Multi-Stage Pipeline Execution</h1>
    <div id="console">Connecting to streaming stack...<br></div>
    <script>
        const div = document.getElementById('console');
        const src = new EventSource('/stream-log');
        src.onmessage = function(e) {
            if (e.data === "CLEAR_DEFAULT") { div.innerHTML = ""; return; }
            if (e.data === "PIPELINE_COMPLETE") {
                div.innerHTML += "<br><strong style='color:#38bdf8;'>Pipeline finished. <a href=\"/\" style='color:#66fcf1;'>View Compiled Matrix</a></strong>";
                src.close(); return;
            }
            div.innerHTML += e.data;
            div.scrollTop = div.scrollHeight;
        };
        src.onerror = function() { src.close(); };
    </script></body></html>
    """


@app.route('/stream-log')
def stream_log():
    def generate_events():
        yield "data: <h3>System Health Check: Verifying Storage Mount Permissions...</h3>\n\n"
        yield "data: CLEAR_DEFAULT\n\n"

        # Diverts runtime logs directly out via the server-sent events socket
        run_pipeline_logic(lambda text: print(f"data: {text}\n\n"))

        yield "data: PIPELINE_COMPLETE\n\n"

    return Response(generate_events(), mimetype='text/event-stream')


@app.route('/execute-worker', methods=['POST'])
def execute_worker():
    """Target endpoint invoked cleanly by Cloud Tasks via secure HTTPS POST.
    Flushes straight to container stdout for native Cloud Run log capture."""
    print("Cloud Task worker picked up execution. Starting pipeline...", flush=True)

    success = run_pipeline_logic(lambda text: print(f"[Worker Log] {text}", flush=True))

    if success:
        return "Pipeline execution completed cleanly.", 200
    else:
        return "Pipeline execution completed with runtime failures.", 500


@app.route('/visuals/graphs/<filename>')
def serve_trend_graphs(filename):
    target_graph_path = os.path.join(config.GRAPHS_DIR, filename)
    if not os.path.exists(target_graph_path):
        return f"Graph file {filename} not found on the active storage volume.", 404
    with open(target_graph_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)