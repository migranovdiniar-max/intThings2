import abc
import pymongo
import datetime
import threading
from statistics import mean, median, stdev


class Thing(abc.ABC):
    def __init__(self, name):
        self.name = name
        print(f'[Thing] Created: {name}')

    @abc.abstractmethod
    def connect(self, *args):
        pass


class Sensor(Thing):
    MIN_VALUE = -50.0
    MAX_VALUE = 150.0

    def __init__(self, unit, name):
        super().__init__(name)
        self.unit = unit
        self.value = 0.0
        self.power = 'on'
        print('[Sensor] Created')

    def validate(self, raw_value):
        """Return (float_value, error_message_or_None)."""
        try:
            val = float(raw_value)
        except (ValueError, TypeError):
            return None, f'Not a number: {raw_value!r}'
        if not (self.MIN_VALUE <= val <= self.MAX_VALUE):
            return None, (f'Out of range [{self.MIN_VALUE}, {self.MAX_VALUE}]: {val}')
        return val, None

    def connect(self, request):
        super().connect()
        raw = request.args.get('value', '')
        val, err = self.validate(raw)
        if err:
            print(f'[Sensor] Validation failed — {err}')
            return {'power': self.power, 'error': err}
        self.value = val
        return {'power': self.power}


class Heater(Thing):
    def __init__(self, name, switch_on_temperature):
        super().__init__(name)
        self.power = 'Off'
        self.switch_on_temperature = switch_on_temperature
        # Новые параметры для адаптивного управления
        self.use_adaptive_mode = False
        self.adaptive_threshold = switch_on_temperature
        self.anomaly_mode = False

    def connect(self):
        super().connect()
        return {
            'heater_power': self.power,
            'adaptive_mode': self.use_adaptive_mode,
            'threshold': self.adaptive_threshold if self.use_adaptive_mode else self.switch_on_temperature,
            'anomaly_mode': self.anomaly_mode
        }

    def auto_power(self, temperature):
        """Автоматическое управление с учетом адаптивного порога"""
        threshold = self.adaptive_threshold if self.use_adaptive_mode else self.switch_on_temperature
        self.power = 'On' if temperature < threshold else 'Off'

    def set_adaptive_threshold(self, new_threshold):
        """Установка адаптивного порога на основе анализа данных"""
        if -50 <= new_threshold <= 150:
            self.adaptive_threshold = new_threshold
            self.use_adaptive_mode = True
            return True
        return False

    def reset_to_default(self):
        """Сброс к стандартному порогу"""
        self.use_adaptive_mode = False
        self.adaptive_threshold = self.switch_on_temperature


class Logger:
    TEMP_MIN = -50.0
    TEMP_MAX = 150.0

    def __init__(self, db_name: str, mongo_uri: str):
        self.current_temperature = None
        self.current_heater_state = None

        print(f'[Logger] Connecting to MongoDB...')
        self.client = pymongo.MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._timer: threading.Timer | None = None
        self._analysis_timer: threading.Timer | None = None
        print(f'[Logger] Connected to DB: {db_name}')

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _validate_temperature(self, value):
        try:
            val = float(value)
        except (ValueError, TypeError):
            return None, f'Expected a number, got {value!r}'
        if not (self.TEMP_MIN <= val <= self.TEMP_MAX):
            return None, (
                f'Temperature {val} outside valid range '
                f'[{self.TEMP_MIN}, {self.TEMP_MAX}]'
            )
        return val, None

    def _log_error(self, source: str, message: str):
        self.db['Errors'].insert_one({
            'timeStamp': self._now(),
            'source': source,
            'message': message,
        })
        print(f'[Logger][ERROR] {source}: {message}')

    def insert_temperature(self, new_data):
        val, err = self._validate_temperature(new_data)
        if err:
            self._log_error('insert_temperature', err)
            return None

        if val == self.current_temperature:
            print('[Logger] Temperature unchanged — skipping')
            return None

        self.current_temperature = val
        result = self.db['Temperature'].insert_one({
            'timeStamp': self._now(),
            'Temperature': val,
            'unit': 'C',
        })
        print(f'[Logger] Temperature logged: {val} °C')
        return result

    def insert_heater_event(self, new_state: str):
        allowed = {'On', 'Off'}
        if new_state not in allowed:
            self._log_error(
                'insert_heater_event',
                f'Invalid heater state: {new_state!r}. Allowed: {allowed}',
            )
            return None

        if new_state == self.current_heater_state:
            print('[Logger] Heater state unchanged — skipping')
            return None

        self.current_heater_state = new_state
        result = self.db['HeaterEvents'].insert_one({
            'timeStamp': self._now(),
            'heaterState': new_state,
        })
        print(f'[Logger] Heater event logged: {new_state}')
        return result

    # ═══════════════ СИСТЕМА АНАЛИЗА ДАННЫХ ═══════════════════════════════════

    def get_recent_temperatures(self, limit=100):
        """Получение последних N значений температуры из БД"""
        try:
            cursor = self.db['Temperature'].find(
                {},
                {'Temperature': 1, '_id': 0}
            ).sort('_id', -1).limit(limit)

            temperatures = [doc['Temperature'] for doc in cursor]
            return temperatures
        except Exception as e:
            print(f'[Analyzer] Error fetching temperatures: {e}')
            return []

    def calculate_statistics(self, data=None):
        """
        Расчет статистических характеристик:
        - Среднее значение (mean)
        - Максимальное значение (max)
        - Минимальное значение (min)
        - Медиана (median)
        - Стандартное отклонение (std)
        """
        if data is None:
            data = self.get_recent_temperatures(50)

        if not data or len(data) < 2:
            return {
                'error': 'Недостаточно данных для анализа',
                'count': len(data)
            }

        try:
            avg = mean(data)
            stats = {
                'count': len(data),
                'mean': round(avg, 2),
                'median': round(median(data), 2),
                'max': round(max(data), 2),
                'min': round(min(data), 2),
                'std': round(stdev(data), 2) if len(data) > 1 else 0,
                'range': round(max(data) - min(data), 2)
            }

            # Сохраняем результаты анализа в БД
            self.db['AnalysisResults'].insert_one({
                'timeStamp': self._now(),
                'period': 'recent_50',
                'statistics': stats
            })
            print(f'[Analyzer] Statistics calculated: mean={stats["mean"]}°C, std={stats["std"]}°C')

            return stats
        except Exception as e:
            self._log_error('calculate_statistics', str(e))
            return {'error': str(e)}

    def detect_anomalies(self, data=None):
        """
        Обнаружение аномалий на основе правила трёх сигм.
        Аномалия: значение выходит за пределы avg ± 2*std
        """
        if data is None:
            data = self.get_recent_temperatures(50)

        if len(data) < 3:
            return {'anomalies': [], 'message': 'Недостаточно данных'}

        avg = mean(data)
        std = stdev(data)

        anomalies = []
        for i, val in enumerate(data):
            if abs(val - avg) > 2 * std:
                anomalies.append({
                    'value': val,
                    'deviation': round(abs(val - avg), 2),
                    'index': i
                })

        result = {
            'threshold_upper': round(avg + 2 * std, 2),
            'threshold_lower': round(avg - 2 * std, 2),
            'anomalies_count': len(anomalies),
            'anomalies': anomalies,
            'is_anomaly_detected': len(anomalies) > 0
        }

        # Если обнаружены аномалии, логируем их
        if result['is_anomaly_detected']:
            self.db['Anomalies'].insert_one({
                'timeStamp': self._now(),
                'statistics': {
                    'mean': round(avg, 2),
                    'std': round(std, 2)
                },
                'anomalies': anomalies
            })
            print(f'[Analyzer] ⚠ Detected {len(anomalies)} anomalies!')

        return result

    def predict_next_value(self):
        """
        Предсказание следующего значения на основе линейного тренда
        последних 10 значений
        """
        data = self.get_recent_temperatures(10)
        if len(data) < 3:
            return {'error': 'Недостаточно данных для предсказания'}

        # Данные приходят в обратном порядке (новые первые)
        data_reversed = list(reversed(data))

        # Простой линейный тренд: среднее изменение между последовательными точками
        changes = []
        for i in range(1, len(data_reversed)):
            changes.append(data_reversed[i] - data_reversed[i - 1])

        avg_change = mean(changes)
        last_value = data_reversed[-1]
        predicted = last_value + avg_change

        # Ограничиваем предсказание допустимым диапазоном
        predicted = max(self.TEMP_MIN, min(self.TEMP_MAX, predicted))

        result = {
            'last_value': last_value,
            'avg_change': round(avg_change, 2),
            'predicted_next': round(predicted, 2),
            'trend': 'rising' if avg_change > 0.1 else 'falling' if avg_change < -0.1 else 'stable',
            'confidence': 'high' if abs(avg_change) < 5 else 'medium' if abs(avg_change) < 15 else 'low'
        }

        # Сохраняем предсказание
        self.db['Predictions'].insert_one({
            'timeStamp': self._now(),
            'prediction': result
        })

        return result

    def validate_data_quality(self):
        """
        Оценка качества данных на основе статистических характеристик.
        Используется для определения адекватности получаемых данных.
        """
        stats = self.calculate_statistics()
        if 'error' in stats:
            return {'status': 'error', 'message': stats['error']}

        issues = []
        quality_score = 100

        # Проверка 1: Слишком большое стандартное отклонение
        if stats['std'] > 20:
            issues.append('Высокая вариабельность данных (std > 20°C)')
            quality_score -= 30

        # Проверка 2: Мало данных для анализа
        if stats['count'] < 10:
            issues.append('Недостаточный объем данных для надежного анализа')
            quality_score -= 20

        # Проверка 3: Наличие аномалий
        anomalies = self.detect_anomalies()
        if anomalies['is_anomaly_detected']:
            issues.append(f'Обнаружено {anomalies["anomalies_count"]} аномалий')
            quality_score -= 20 * anomalies['anomalies_count']

        quality_score = max(0, quality_score)

        result = {
            'quality_score': quality_score,
            'rating': 'отличное' if quality_score >= 80 else 'хорошее' if quality_score >= 60 else 'удовлетворительное' if quality_score >= 40 else 'низкое',
            'issues': issues,
            'statistics': stats
        }

        # Сохраняем оценку качества
        self.db['DataQuality'].insert_one({
            'timeStamp': self._now(),
            'assessment': result
        })

        return result

    def auto_adjust_threshold(self, heater_ref):
        """
        Автоматическая регулировка порога нагревателя на основе статистики.
        Если средняя температура значительно отличается от порога 25°C,
        система адаптирует порог для оптимизации.
        """
        stats = self.calculate_statistics()
        if 'error' in stats:
            return {'status': 'error', 'message': stats['error']}

        current_mean = stats['mean']
        current_std = stats['std']
        current_threshold = heater_ref.adaptive_threshold if heater_ref.use_adaptive_mode else heater_ref.switch_on_temperature

        adjustment = None
        reason = None

        # Если средняя температура стабильно выше порога + 2*std
        if current_mean > current_threshold + 2 * current_std:
            new_threshold = current_threshold + 2
            adjustment = 'increase'
            reason = f'Средняя температура ({current_mean:.1f}°C) стабильно выше порога ({current_threshold}°C)'

        # Если средняя температура стабильно ниже порога - 2*std
        elif current_mean < current_threshold - 2 * current_std:
            new_threshold = current_threshold - 2
            adjustment = 'decrease'
            reason = f'Средняя температура ({current_mean:.1f}°C) стабильно ниже порога ({current_threshold}°C)'

        if adjustment:
            heater_ref.set_adaptive_threshold(new_threshold)

            result = {
                'status': 'adjusted',
                'adjustment': adjustment,
                'old_threshold': current_threshold,
                'new_threshold': new_threshold,
                'reason': reason,
                'current_mean': round(current_mean, 2),
                'current_std': round(current_std, 2)
            }

            # Логируем изменение порога
            self.db['ThresholdAdjustments'].insert_one({
                'timeStamp': self._now(),
                'adjustment': result
            })

            print(f'[Analyzer] 🔧 Threshold adjusted: {current_threshold}°C → {new_threshold}°C ({reason})')
            return result
        else:
            return {
                'status': 'unchanged',
                'current_threshold': current_threshold,
                'current_mean': round(current_mean, 2),
                'message': 'Порог не требует корректировки'
            }

    def start_periodic(self, sensor: 'Sensor', heater: 'Heater',
                       interval_sec: float = 10.0):
        """Запуск периодической записи данных"""
        def _tick():
            self.insert_temperature(sensor.value)
            self.insert_heater_event(heater.power)
            self._timer = threading.Timer(interval_sec, _tick)
            self._timer.daemon = True
            self._timer.start()

        self._timer = threading.Timer(interval_sec, _tick)
        self._timer.daemon = True
        self._timer.start()
        print(f'[Logger] Periodic logging started (every {interval_sec}s)')

    def start_periodic_analysis(self, heater_ref, interval_sec=60.0):
        """Запуск периодического анализа данных"""
        def _analyze():
            print('[Analyzer] Running periodic analysis...')

            # Расчет статистики
            stats = self.calculate_statistics()
            if 'error' not in stats:
                print(f'[Analyzer] Stats: mean={stats["mean"]}°C, std={stats["std"]}°C')

            # Проверка на аномалии
            anomalies = self.detect_anomalies()
            if anomalies['is_anomaly_detected']:
                print(f'[Analyzer] ⚠ Anomalies detected: {anomalies["anomalies_count"]}')
                heater_ref.anomaly_mode = True
            else:
                heater_ref.anomaly_mode = False

            # Предсказание следующего значения
            prediction = self.predict_next_value()
            if 'error' not in prediction:
                print(f'[Analyzer] Prediction: next={prediction["predicted_next"]}°C, trend={prediction["trend"]}')

            # Автоматическая регулировка порога
            adjustment = self.auto_adjust_threshold(heater_ref)
            if adjustment['status'] == 'adjusted':
                print(f'[Analyzer] 🔧 Auto-adjusted threshold: {adjustment["new_threshold"]}°C')

            # Оценка качества данных
            quality = self.validate_data_quality()
            print(f'[Analyzer] Data quality: {quality["rating"]} (score: {quality["quality_score"]})')

            # Перезапуск таймера
            self._analysis_timer = threading.Timer(interval_sec, _analyze)
            self._analysis_timer.daemon = True
            self._analysis_timer.start()

        self._analysis_timer = threading.Timer(interval_sec, _analyze)
        self._analysis_timer.daemon = True
        self._analysis_timer.start()
        print(f'[Analyzer] Periodic analysis started (every {interval_sec}s)')

    def stop_periodic(self):
        if self._timer:
            self._timer.cancel()
            print('[Logger] Periodic logging stopped')
        if self._analysis_timer:
            self._analysis_timer.cancel()
            print('[Analyzer] Periodic analysis stopped')