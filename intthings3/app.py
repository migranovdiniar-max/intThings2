from flask import Flask, request, render_template, jsonify
import things
import os

app = Flask(__name__)

# КОНФИГУРАЦИЯ БАЗЫ ДАННЫХ 
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')

temp_sensor = things.Sensor('C', 'temperature_sensor')
heater      = things.Heater('Heater1', switch_on_temperature=25)

logger      = things.Logger('IOT_logger_db', mongo_uri=MONGO_URI)

# Запуск периодических задач
logger.start_periodic(temp_sensor, heater, interval_sec=30)
logger.start_periodic_analysis(heater, interval_sec=60)  # Анализ каждую минуту


# ═══════════════ БАЗОВЫЕ МАРШРУТЫ ═══════════════════════════════════════════

@app.route('/connect')
def connect():
    """Датчик температуры передаёт новое значение."""
    response = temp_sensor.connect(request)

    if 'error' not in response:
        heater.auto_power(temp_sensor.value)
        logger.insert_temperature(temp_sensor.value)
        logger.insert_heater_event(heater.power)

    return jsonify(response)


@app.route('/connect_heater')
def connect_heater():
    """Возвращает текущее состояние нагревателя."""
    response = heater.connect()
    return jsonify(response)


# ═══════════════ МАРШРУТЫ АНАЛИЗА ДАННЫХ ═════════════════════════════════════

@app.route('/analysis/statistics')
def get_statistics():
    """Расчет статистических характеристик"""
    stats = logger.calculate_statistics()
    return jsonify(stats)


@app.route('/analysis/anomalies')
def get_anomalies():
    """Обнаружение аномалий"""
    anomalies = logger.detect_anomalies()
    return jsonify(anomalies)


@app.route('/analysis/predict')
def get_prediction():
    """Предсказание следующего значения"""
    prediction = logger.predict_next_value()
    return jsonify(prediction)


@app.route('/analysis/quality')
def get_data_quality():
    """Оценка качества данных"""
    quality = logger.validate_data_quality()
    return jsonify(quality)


@app.route('/analysis/adjust-threshold')
def adjust_threshold():
    """Автоматическая регулировка порога нагревателя"""
    result = logger.auto_adjust_threshold(heater)
    return jsonify(result)


@app.route('/analysis/reset-threshold')
def reset_threshold():
    """Сброс порога нагревателя к стандартному значению"""
    heater.reset_to_default()
    return jsonify({
        'status': 'reset',
        'threshold': heater.switch_on_temperature,
        'adaptive_mode': False
    })


@app.route('/analysis/full-report')
def get_full_report():
    """Полный аналитический отчет"""
    report = {
        'timestamp': logger._now(),
        'statistics': logger.calculate_statistics(),
        'anomalies': logger.detect_anomalies(),
        'prediction': logger.predict_next_value(),
        'data_quality': logger.validate_data_quality(),
        'heater_status': heater.connect()
    }
    return jsonify(report)


@app.route('/')
def index():
    return render_template('sensor_emulator.html')


if __name__ == '__main__':
    app.run(debug=False)