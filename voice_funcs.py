import json
import logging
import time
from collections.abc import Callable

import httpx

logger = logging.getLogger(__name__)
logger.setLevel("INFO")

class VoiceModel:
    '''
    语音识别源基类：transcribe_data/transcribe_url 均为 bytes/str -> str | None
    不可用（失败/冷却中）时返回 None，由上层 VoiceRecognition 决定回退
    '''
    def transcribe_data(self, audio_data: bytes) -> str | None:
        raise NotImplementedError

    def transcribe_url(self, audio_url: str) -> str | None:
        raise NotImplementedError

    def stop(self):
        pass

class AliyunVoice(VoiceModel):
    '''
    阿里云百炼（DashScope）录音文件识别：创建异步任务后轮询结果
    transcribe_data 依赖 link_factory 将音频转成可公网访问的临时链接
    失败/冷却中返回 None
    '''

    def __init__(self, key: str, model: str, link_factory: Callable[[bytes], str]):
        self.key = key
        self.model = model
        self.link_factory = link_factory
        self.cooldown_until: float = 0
        self.client = httpx.Client()

    def _check_error(self, resp: httpx.Response, action: str) -> bool:
        """检查 HTTP 状态码；非 200 时记录日志并按错误类型设置冷却，返回 True 表示出错"""
        if resp.status_code == 200:
            return False
        body = resp.text
        if resp.status_code in (401, 402, 403): # Key 无效/余额不足，短时间内重试无意义
            logger.error(f"{action} 不可用({resp.status_code}): {body}")
            self.cooldown_until = time.time() + 600
        elif resp.status_code == 429: # 触发限速，短暂冷却
            logger.warning(f"{action} 触发限速(429): {body}")
            self.cooldown_until = time.time() + 60
        else:
            logger.error(f"{action} 失败({resp.status_code}): {body}")
        return True

    def _create_task(self, audio_url: str) -> str | None:
        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        data = {"model": self.model, "input": {"file_urls": [audio_url]}}
        resp = self.client.post(url, json=data, headers=headers, timeout=15)
        if self._check_error(resp, "阿里云任务创建"):
            return None
        try:
            return resp.json()["output"]["task_id"]
        except (ValueError, KeyError, TypeError):
            logger.error(f"阿里云任务创建响应异常: {resp.text}")
            return None

    def _wait_result(self, task_id: str) -> str | None:
        url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {self.key}"}
        start = time.time()
        time.sleep(2) # 任务刚创建时查询通常仍是 PENDING，先等待避免无谓请求

        while time.time() - start < 600:
            resp = self.client.get(url, headers=headers, timeout=10)
            if self._check_error(resp, "阿里云任务查询"):
                return None
            try:
                output = resp.json()["output"]
                status = output["task_status"]
                if status == "SUCCEEDED":
                    return output["results"][0]["transcription_url"]
                elif status in ("RUNNING", "PENDING"):
                    time.sleep(1)
                else:
                    # 状态变成 FAILED 或其他
                    logger.error(f"阿里云语音识别任务失败，状态为 [{status}]: {resp.text}")
                    return None
            except (ValueError, KeyError, IndexError, TypeError):
                logger.error(f"阿里云返回结构异常无法解析: {resp.text}")
                return None

        logger.error("阿里云语音识别超时（超过10分钟）")
        return None

    def transcribe_data(self, audio_data: bytes) -> str | None:
        if self.cooldown_until > time.time():
            return None
        if not audio_data:
            return None
        try:
            audio_url = self.link_factory(audio_data)
        except Exception as e:
            logger.exception(f"阿里云语音识别生成临时下载链接失败: {e}")
            return None
        return self.transcribe_url(audio_url)

    def transcribe_url(self, audio_url: str) -> str | None:
        if self.cooldown_until > time.time():
            return None
        if not audio_url:
            return None
        try:
            task_id = self._create_task(audio_url)
            if task_id is None:
                return None
            result_url = self._wait_result(task_id)
            if result_url is None:
                return None

            resp = self.client.get(result_url, timeout=20, follow_redirects=True)
            if resp.status_code != 200:
                logger.error(f"阿里云语音识别结果下载失败({resp.status_code}): {resp.text}")
                return None
            try:
                res = resp.json()
                return res["transcripts"][0]["text"]
            except (ValueError, KeyError, IndexError, TypeError):
                logger.error(f"阿里云返回结果中未包含有效文字: {resp.text}")
                return None
        except httpx.HTTPError as e:
            logger.exception(f"请求阿里云语音识别失败: {e}")
            return None

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()

class AzureVoice(VoiceModel):
    '''
    Azure 语音转文字：支持音频 URL 与二进制数据两种提交方式
    失败/冷却中返回 None
    '''

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.cooldown_until: float = 0
        self.client = httpx.Client()

    def _transcribe(self, audio_data: bytes | None = None, audio_url: str | None = None) -> str | None:
        if self.cooldown_until > time.time():
            return None
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        params: dict = {"headers": headers, "timeout": 30}
        if audio_data is not None:
            params["files"] = {"audio": ("audio", audio_data, "application/octet-stream")}
        elif audio_url is not None:
            params["data"] = {"definition": json.dumps({"audioUrl": audio_url}, ensure_ascii=False)}
        else:
            return None

        try:
            resp = self.client.post(self.url, **params)
        except httpx.HTTPError as e:
            logger.exception(f"请求 Azure 语音识别失败: {e}")
            return None

        if resp.status_code != 200:
            body = resp.text
            if resp.status_code in (401, 402, 403): # Key 无效/余额不足，短时间内重试无意义
                logger.error(f"Azure 语音识别不可用({resp.status_code}): {body}")
                self.cooldown_until = time.time() + 600
            elif resp.status_code == 429: # 触发限速，短暂冷却
                logger.warning(f"Azure 语音识别触发限速(429): {body}")
                self.cooldown_until = time.time() + 60
            else:
                logger.error(f"Azure 语音识别失败({resp.status_code}): {body}")
            return None

        try:
            return "\n".join(i["text"] for i in resp.json()["phrases"] if "text" in i)
        except (ValueError, KeyError, TypeError):
            logger.error(f"Azure 返回了无法解析的内容: {resp.text}")
            return None

    def transcribe_url(self, audio_url: str) -> str | None:
        if not audio_url:
            return None
        return self._transcribe(audio_url=audio_url)

    def transcribe_data(self, audio_data: bytes) -> str | None:
        if not audio_data:
            return None
        return self._transcribe(audio_data=audio_data)

    def stop(self):
        """关闭底层 HTTP 连接池"""
        self.client.close()

class VoiceRecognition:
    '''
    语音识别源组合：从轮询起点开始依次尝试各识别源，返回第一个非 None 结果
    全部不可用时抛出异常，由接口层决定错误响应
    '''

    def __init__(self, models: list[VoiceModel]):
        self.models = models
        self.balancing_index = 0

    def transcribe_from_url(self, audio_url: str) -> str:
        count = len(self.models)
        for offset in range(count):
            index = (self.balancing_index + offset) % count
            result = self.models[index].transcribe_url(audio_url)
            if result is not None:
                self.balancing_index = (index + 1) % count # 成功后将轮询起点移到下一个源
                return result
        raise RuntimeError("所有语音识别服务均不可用")

    def transcribe_from_data(self, audio_data: bytes) -> str:
        count = len(self.models)
        for offset in range(count):
            index = (self.balancing_index + offset) % count
            result = self.models[index].transcribe_data(audio_data)
            if result is not None:
                self.balancing_index = (index + 1) % count # 成功后将轮询起点移到下一个源
                return result
        raise RuntimeError("所有语音识别服务均不可用")

    def stop(self):
        for model in self.models:
            model.stop()
