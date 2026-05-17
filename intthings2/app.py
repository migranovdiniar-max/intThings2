from flask import Flask, request, render_template, jsonify
import things

app = Flask(__name__)

# КОНФИГУРАЦИЯ БАЗЫ ДАННЫХ 
MONGO_URI = "mongodb+srv://migranovdiniar_db_user:bQc5ACn4mniSR4J@cluster0.pnbh6cy.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

temp_sensor = things.Sensor('C', 'temperature_sensor')
heater      = things.Heater('Heater1', switch_on_temperature=25)

logger      = things.Logger('IOT_logger_db', mongo_uri=MONGO_URI)

logger.start_periodic(temp_sensor, heater, interval_sec=30)


# маршруты 

@app.route('/connect')
def connect():
    """Датчик температуры передаёт новое значение."""
    response = temp_sensor.connect(request)

    if 'error' not in response:
        # обновляем состояние нагревателя
        heater.auto_power(temp_sensor.value)
        # логируем температуру и событие нагревателя
        logger.insert_temperature(temp_sensor.value)
        logger.insert_heater_event(heater.power)

    return jsonify(response)


@app.route('/connect_heater')
def connect_heater():
    """Возвращает текущее состояние нагревателя."""
    response = heater.connect()
    return jsonify(response)


@app.route('/')
def index():
    return render_template('sensor_emulator.html')


if __name__ == '__main__':
    app.run(debug=False)