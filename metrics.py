import time
import json
import os
from datetime import datetime
from functools import wraps


class MetricsCollector:
    def __init__(self, metrics_dir):
        self.metrics_dir = metrics_dir
        self.metrics_file = os.path.join(
            metrics_dir, 'performance_metrics.json')
        self.current_metrics = self._load_metrics()

    def _load_metrics(self):
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return self._create_initial_metrics()
        return self._create_initial_metrics()

    def _create_initial_metrics(self):
        return {
            'total_messages_processed': 0,
            'total_audio_duration': 0,
            'average_processing_time': 0,
            'success_rate': 0,
            'operations': {
                'voice_processing': {'total_time': 0, 'count': 0},
                'audio_splitting': {'total_time': 0, 'count': 0},
                'speech_recognition': {'total_time': 0, 'count': 0}
            }
        }

    def update_metrics(self, operation, duration, success=True):
        self.current_metrics['operations'][operation]['total_time'] += duration
        self.current_metrics['operations'][operation]['count'] += 1

        # Обновление общей статистики
        if operation == 'voice_processing':
            self.current_metrics['total_messages_processed'] += 1

        # Сохранение метрик
        self._save_metrics()

    def _save_metrics(self):
        with open(self.metrics_file, 'w') as f:
            json.dump(self.current_metrics, f, indent=2)

    def get_metrics_summary(self):
        summary = {}
        for op, data in self.current_metrics['operations'].items():
            if data['count'] > 0:
                avg_time = data['total_time'] / data['count']
                summary[op] = {
                    'average_time': round(avg_time, 2),
                    'total_operations': data['count']
                }
        return summary


def measure_time(metrics_collector, operation):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                metrics_collector.update_metrics(
                    operation, duration, success=True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics_collector.update_metrics(
                    operation, duration, success=False)
                raise e
        return wrapper
    return decorator
