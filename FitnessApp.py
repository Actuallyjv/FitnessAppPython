import os
import datetime
import json
from PyQt5 import QtWidgets, QtCore


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%y-%m-%d")
        return super().default(obj)


class BodyMeasurementsTracker(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Body Measurements Tracker")
        self.measurements = []
        self.load_measurements()

        layout = QtWidgets.QVBoxLayout()

        # ... (Rest of the code remains the same) ...

    def load_measurements(self):
        filepath = self.get_file_path("measurements.json")
        try:
            with open(filepath, "r") as file:
                self.measurements = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.measurements = []

    def calculate_relevant_data(self):
        weights = [m["Weight"] for m in self.measurements if m["Weight"] is not None]
        biceps = [
            m.get("Bicep") for m in self.measurements if m.get("Bicep") is not None
        ]
        chests = [m["Chest"] for m in self.measurements if m["Chest"] is not None]
        waists = [m["Waist"] for m in self.measurements if m["Waist"] is not None]
        thighs = [m["Thigh"] for m in self.measurements if m["Thigh"] is not None]
        calves = [m["Calf"] for m in self.measurements if m["Calf"] is not None]

        if not weights:
            self.status_label.setText("No weight measurements available.")
            self.status_label.setStyleSheet("color: #FF0000")
            return

        average_weight = sum(weights) / len(weights)
        average_bicep = sum(biceps) / len(biceps) if biceps else None
        average_chest = sum(chests) / len(chests) if chests else None
        average_waist = sum(waists) / len(waists) if waists else None
        average_thigh = sum(thighs) / len(thighs) if thighs else None
        average_calf = sum(calves) / len(calves) if calves else None

        result_text = (
            f"Average Weight: {average_weight:.2f} kilograms\n"
            f"Average Bicep Circumference: {average_bicep:.2f} centimeters\n"
            if average_bicep is not None
            else "" f"Average Chest Circumference: {average_chest:.2f} centimeters\n"
            if average_chest is not None
            else "" f"Average Waist Circumference: {average_waist:.2f} centimeters\n"
            if average_waist is not None
            else "" f"Average Thigh Circumference: {average_thigh:.2f} centimeters\n"
            if average_thigh is not None
            else "" f"Average Calf Circumference: {average_calf:.2f} centimeters\n"
            if average_calf is not None
            else ""
        )
        self.measurements_text.clear()
        self.measurements_text.setPlainText("Relevant data:\n\n" + result_text)
        self.status_label.setText("")

    def calculate_trends(self, period):
        now = datetime.datetime.now()
        relevant_measurements = [
            m
            for m in self.measurements
            if datetime.datetime.strptime(m["Timestamp"], "%y-%m-%d")
            > (now - datetime.timedelta(days=period))
        ]
        if not relevant_measurements:
            return None

        latest_measurement = relevant_measurements[-1]
        trend_data = {}
        for key in latest_measurement.keys():
            if key != "Timestamp":
                latest_value = latest_measurement[key]
                past_values = [
                    m[key] for m in relevant_measurements if m[key] is not None
                ]
                if past_values:
                    difference = latest_value - past_values[0]
                    trend_data[key] = difference

        return trend_data

    def display_trends(self, period):
        trend_data = self.calculate_trends(period)
        if not trend_data:
            return

        self.measurements_text.clear()
        self.measurements_text.setPlainText(
            f"Trends in measurements over the last {period} days:\n\n"
        )
        for key, value in trend_data.items():
            self.measurements_text.appendPlainText(f"{key}: {value:.2f}")

    # ... (Rest of the code remains the same) ...


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    window = BodyMeasurementsTracker()
    window.show()
    app.exec_()
