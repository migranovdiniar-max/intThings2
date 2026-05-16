from flask import Flask, render_template_string, jsonify, request
from devices import TemperatureSensor, HumiditySensor

app = Flask(__name__)

devices = {
    "temp1": TemperatureSensor("temp1", "kitchen"),
    "hum1": HumiditySensor("hum1", "living room")
}

for d in devices.values():
    print(d.connect())

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>IoT Dashboard</title>
    <style>
        body { font-family: Arial; margin: 40px; background: #f0f0f0; }
        h1 { color: #333; }
        .device { background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        button { background: #007BFF; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 20px; }
        button:hover { background: #0056b3; }
        pre { background: #eee; padding: 10px; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>📡 IoT Dashboard</h1>
    <h2>Devices</h2>
    <div id="devices"></div>
    <button onclick="refreshData()">🔄 Refresh all data</button>
    <h3>Console log</h3>
    <pre id="log"></pre>

    <script>
        async function refreshData() {
            const res = await fetch('/api/data');
            const data = await res.json();
            const container = document.getElementById('devices');
            container.innerHTML = '';
            for (let id in data) {
                const dev = data[id];
                container.innerHTML += `
                    <div class="device">
                        <strong>${dev.device_id}</strong> (${dev.type}) - ${dev.location}<br>
                        Value: ${dev.value} ${dev.unit}
                    </div>
                `;
            }
            // Лог
            const logRes = await fetch('/api/log');
            const logText = await logRes.text();
            document.getElementById('log').innerText = logText;
        }
        refreshData();
        setInterval(refreshData, 3000);
    </script>
</body>
</html>
"""

log_messages = []

def add_log(msg):
    log_messages.append(msg)
    print(msg)

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    result = {}
    for device_id, device in devices.items():
        result[device_id] = device.get_data()
        add_log(f"GET data from {device_id}")
    return jsonify(result)

@app.route('/api/log')
def get_log():
    return "\n".join(log_messages[-20:])  # последние 20 строк

if __name__ == '__main__':
    add_log("Starting Flask IoT application...")
    print("Открыть в браузере: http://127.0.0.1:5000\n")
    app.run(debug=True)