from obswebsocket import obsws, requests
from obswebsocket.exceptions import ConnectionFailure



class OBSController:
    def __init__(self, host="localhost", port=4455, password=""):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.connected = False

    def connect(self):
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            print("[OBS] Успешно подключено")
            return True
        except ConnectionFailure as e:
            print(f"[OBS] Ошибка подключения: {e}")
            self.connected = False
            return False
        except Exception as e:
            print(f"[OBS] Неизвестная ошибка: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.ws and self.connected:
            self.ws.disconnect()
            self.connected = False
            print("[OBS] Отключено")

    def switch_scene(self, scene_name: str):
        if not self.connected:
            print("[OBS] Нет подключения")
            return False
        try:
            self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            print(f"[OBS] Переключено на сцену: {scene_name}")
            return True
        except Exception as e:
            print(f"[OBS] Ошибка переключения сцены: {e}")
            return False

    def set_mute(self, source_name: str, muted: bool):
        if not self.connected:
            return False
        try:
            self.ws.call(requests.SetInputMute(inputName=source_name, inputMuted=muted))
            status = "заглушен" if muted else "включён"
            print(f"[OBS] Источник '{source_name}' {status}")
            return True
        except Exception as e:
            print(f"[OBS] Ошибка мьюта {source_name}: {e}")
            return False

    def mute_all_discord(self, sources: list, muted: bool):
        success = True
        for source in sources:
            if not self.set_mute(source, muted):
                success = False
        return success

    def get_current_scene(self):
        if not self.connected:
            return None
        try:
            response = self.ws.call(requests.GetCurrentProgramScene())
            return response.getSceneName()
        except Exception as e:
            print(f"[OBS] Ошибка получения текущей сцены: {e}")
            return None

    def get_all_inputs(self):
        """Возвращает список всех аудио-источников (для отладки)"""
        if not self.connected:
            return []
        try:
            response = self.ws.call(requests.GetInputList())
            inputs = response.getInputs()
            return [inp["inputName"] for inp in inputs]
        except Exception as e:
            print(f"[OBS] Ошибка получения списка источников: {e}")
            return []