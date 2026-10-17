import os
import subprocess
import time
import json
import urllib.request
import urllib.error


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENGINE_DIR = os.path.join(BASE_DIR, "engine")
MODELS_DIR = os.path.join(BASE_DIR, "models")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

SERVER_EXE = os.path.join(ENGINE_DIR, "llama-server.exe")


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_MODEL = "Qwen3-1.7B-Q4_K_M.gguf"

DEFAULT_CPU_THREADS = 2
DEFAULT_CONTEXT_SIZE = 2048
DEFAULT_MAX_TOKENS = 384
DEFAULT_TEMPERATURE = 0.7
DEFAULT_THINKING = False


# ============================================================
# SERVER SETTINGS
# ============================================================

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9931

SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
HEALTH_URL = f"{SERVER_URL}/health"
CHAT_URL = f"{SERVER_URL}/v1/chat/completions"

MODEL_ALIAS = "boltu"


# ============================================================
# RUNTIME STATE
# ============================================================

_current_model = DEFAULT_MODEL

_cpu_threads = DEFAULT_CPU_THREADS
_context_size = DEFAULT_CONTEXT_SIZE
_max_tokens = DEFAULT_MAX_TOKENS
_temperature = DEFAULT_TEMPERATURE
_thinking_enabled = DEFAULT_THINKING

_server_process = None


# ============================================================
# CONVERSATION
# ============================================================

messages = []


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt(model_name):
    model_filename = os.path.basename(model_name)

    # Boltu is currently a Qwen-only build, so keep the model identity
    # completely filename-driven. This automatically covers Qwen3-4B and
    # future Qwen GGUFs without another size-specific branch.
    model_identity = model_filename

    if _thinking_enabled:
        thinking_text = "Thinking is enabled."
    else:
        thinking_text = "Thinking is disabled."

    return f"""
You are Boltu, an offline AI assistant.

Your name is Boltu.

You are powered by the {model_identity} language model.
{model_identity} is the underlying AI model; Boltu is the assistant built around it.

You run locally on the user's computer.

Important facts about yourself:
- You do not have internet access.
- You cannot browse websites or access live information.
- Your knowledge may be outdated.
- You do not know your exact training-data cutoff.
- Never claim that your knowledge extends to the present unless the user has provided that information in the conversation.
- Never invent a training-data date or claim to have access to current events.
- Try to answer the user's question using the knowledge and reasoning available to you.
- If you are uncertain, clearly say what you are uncertain about, but still provide the best useful answer you can.
- Do not fabricate specific facts, citations, sources, quotations, or personal experiences just to make an answer sound complete.
- Do not pretend to have capabilities that you do not have.

Your current underlying model is {model_identity}.
If the user asks which model you are running, answer with that model name.

{thinking_text}

Answer clearly, accurately, and concisely.
For educational questions, explain concepts at an appropriate level and include equations when useful.
""".strip()


def get_system_prompt():
    return build_system_prompt(_current_model)


# ============================================================
# CONFIGURATION
# ============================================================

def get_default_config():
    return {
        "model": DEFAULT_MODEL,
        "cpu_threads": DEFAULT_CPU_THREADS,
        "context_size": DEFAULT_CONTEXT_SIZE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": DEFAULT_TEMPERATURE,
        "thinking": DEFAULT_THINKING,
    }


def load_config():
    global _current_model
    global _cpu_threads
    global _context_size
    global _max_tokens
    global _temperature
    global _thinking_enabled

    os.makedirs(CONFIG_DIR, exist_ok=True)

    config = get_default_config()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)

            if isinstance(saved, dict):
                config.update(saved)

        except Exception:
            pass

    _current_model = str(config.get("model", DEFAULT_MODEL))

    _cpu_threads = validate_cpu_threads(
        config.get("cpu_threads", DEFAULT_CPU_THREADS)
    )

    _context_size = validate_context_size(
        config.get("context_size", DEFAULT_CONTEXT_SIZE)
    )

    _max_tokens = validate_max_tokens(
        config.get("max_tokens", DEFAULT_MAX_TOKENS)
    )

    _temperature = validate_temperature(
        config.get("temperature", DEFAULT_TEMPERATURE)
    )

    _thinking_enabled = bool(
        config.get("thinking", DEFAULT_THINKING)
    )


def save_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)

    config = {
        "model": _current_model,
        "cpu_threads": _cpu_threads,
        "context_size": _context_size,
        "max_tokens": _max_tokens,
        "temperature": _temperature,
        "thinking": _thinking_enabled,
    }

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        return True

    except Exception:
        return False


# ============================================================
# VALIDATION
# ============================================================

def validate_cpu_threads(value):
    try:
        value = int(value)
    except Exception:
        value = DEFAULT_CPU_THREADS

    return max(1, min(8, value))


def validate_context_size(value):
    try:
        value = int(value)
    except Exception:
        value = DEFAULT_CONTEXT_SIZE

    return max(512, min(8192, value))


def validate_max_tokens(value):
    try:
        value = int(value)
    except Exception:
        value = DEFAULT_MAX_TOKENS

    return max(32, min(2048, value))


def validate_temperature(value):
    try:
        value = float(value)
    except Exception:
        value = DEFAULT_TEMPERATURE

    return max(0.0, min(2.0, value))


# ============================================================
# SETTINGS GETTERS
# ============================================================

def get_settings():
    return {
        "cpu_threads": _cpu_threads,
        "context_size": _context_size,
        "max_tokens": _max_tokens,
        "temperature": _temperature,
        "thinking": _thinking_enabled,
    }


def apply_settings(
    cpu_threads,
    context_size,
    max_tokens,
    temperature,
    thinking,
):
    global _cpu_threads
    global _context_size
    global _max_tokens
    global _temperature
    global _thinking_enabled

    _cpu_threads = validate_cpu_threads(cpu_threads)
    _context_size = validate_context_size(context_size)
    _max_tokens = validate_max_tokens(max_tokens)
    _temperature = validate_temperature(temperature)
    _thinking_enabled = bool(thinking)


# ============================================================
# MODEL MANAGEMENT
# ============================================================

def get_available_models():
    if not os.path.exists(MODELS_DIR):
        return []

    models = []

    try:
        for filename in os.listdir(MODELS_DIR):
            if filename.lower().endswith(".gguf"):
                models.append(filename)
    except Exception:
        return []

    models.sort(key=str.lower)

    return models


def get_model_path(model_name):
    if not model_name:
        return None

    filename = os.path.basename(model_name)

    if not filename.lower().endswith(".gguf"):
        return None

    path = os.path.join(MODELS_DIR, filename)

    if not os.path.isfile(path):
        return None

    return path


def get_current_model():
    return _current_model


def set_current_model(model_name):
    global _current_model

    available = get_available_models()

    if model_name not in available:
        return False

    _current_model = model_name

    return True


# ============================================================
# SERVER HEALTH
# ============================================================

def check_server(timeout=1.0):
    try:
        request = urllib.request.Request(
            HEALTH_URL,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            if response.status != 200:
                return False

            data = response.read().decode("utf-8")

            try:
                result = json.loads(data)

                return result.get("status") == "ok"

            except Exception:
                return False

    except Exception:
        return False


# ============================================================
# SERVER START
# ============================================================

def start_server(model_name=None):
    global _server_process
    global _current_model

    if model_name is None:
        model_name = _current_model

    model_path = get_model_path(model_name)

    if model_path is None:
        raise RuntimeError(
            f"Model not found:\n{model_name}"
        )

    if not os.path.isfile(SERVER_EXE):
        raise RuntimeError(
            f"llama-server.exe was not found:\n{SERVER_EXE}"
        )

    # Stop any previous server.
    stop_server()

    _current_model = model_name

    # --------------------------------------------------------
    # Reasoning mode
    # --------------------------------------------------------

    reasoning_mode = "on" if _thinking_enabled else "off"

    # --------------------------------------------------------
    # Server command
    # --------------------------------------------------------

    command = [
        SERVER_EXE,

        "-m",
        model_path,

        "-t",
        str(_cpu_threads),

        "-c",
        str(_context_size),

        "-ngl",
        "0",

        "--reasoning",
        reasoning_mode,

        "--alias",
        MODEL_ALIAS,

        "--host",
        SERVER_HOST,

        "--port",
        str(SERVER_PORT),
    ]

    # --------------------------------------------------------
    # Start server
    # --------------------------------------------------------

    try:
        _server_process = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    except Exception as e:
        _server_process = None

        raise RuntimeError(
            f"Could not start llama-server:\n{e}"
        )

    # --------------------------------------------------------
    # Wait for server
    # --------------------------------------------------------

    start_time = time.time()

    while time.time() - start_time < 60:
        if _server_process is not None:

            return_code = _server_process.poll()

            if return_code is not None:
                _server_process = None

                raise RuntimeError(
                    "llama-server.exe stopped unexpectedly."
                )

        if check_server():
            return True

        time.sleep(0.25)

    # Timeout

    stop_server()

    raise RuntimeError(
        "Timed out while waiting for llama-server."
    )


# ============================================================
# SERVER STOP
# ============================================================

def stop_server():
    global _server_process

    if _server_process is None:
        return

    try:
        if _server_process.poll() is None:
            _server_process.terminate()

            try:
                _server_process.wait(timeout=5)

            except subprocess.TimeoutExpired:
                _server_process.kill()
                _server_process.wait(timeout=2)

    except Exception:
        try:
            _server_process.kill()
        except Exception:
            pass

    finally:
        _server_process = None


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def reset_conversation():
    global messages

    messages = [
        {
            "role": "system",
            "content": get_system_prompt(),
        }
    ]


def add_user_message(text):
    messages.append(
        {
            "role": "user",
            "content": text,
        }
    )


def add_assistant_message(text):
    messages.append(
        {
            "role": "assistant",
            "content": text,
        }
    )


# ============================================================
# STREAMING CHAT
# ============================================================

def stream_chat(
    token_callback=None,
    thinking_callback=None,
    error_callback=None,
    stats_callback=None,
):
    """
    Streams the current conversation through llama.cpp.

    Returns the complete assistant response.

    If supported by llama.cpp, stats_callback receives exact completion-token
    usage and server-side generation timing.
    """

    if not check_server():
        error = "Model server is not running."

        if error_callback:
            error_callback(error)

        return ""

    payload = {
        "model": MODEL_ALIAS,

        "messages": messages,

        "temperature": _temperature,

        "max_tokens": _max_tokens,

        "stream": True,

        # Ask llama.cpp to include exact token usage and generation timings
        # in the final streaming chunk.
        "stream_options": {
            "include_usage": True
        },

        # Explicitly tell the chat template whether
        # thinking is enabled.
        "chat_template_kwargs": {
            "enable_thinking": _thinking_enabled
        },
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        CHAT_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    full_answer = ""
    full_reasoning = ""

    # Exact server-reported generation statistics, when available.
    usage_stats = None
    timing_stats = None

    try:
        with urllib.request.urlopen(
            request,
            timeout=300
        ) as response:

            while True:
                raw_line = response.readline()

                if not raw_line:
                    break

                line = raw_line.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

                if not line:
                    continue

                # SSE format:
                # data: {...}

                if not line.startswith("data:"):
                    continue

                data_text = line[5:].strip()

                if data_text == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_text)

                except json.JSONDecodeError:
                    continue

                # ------------------------------------------------
                # API error
                # ------------------------------------------------

                if "error" in chunk:

                    error = chunk["error"]

                    if isinstance(error, dict):
                        error = error.get(
                            "message",
                            str(error)
                        )

                    if error_callback:
                        error_callback(str(error))

                    return full_answer

                # ------------------------------------------------
                # Usage / timing statistics
                #
                # The final llama.cpp streaming chunk can contain usage
                # and timings, and may have an empty choices array.
                # ------------------------------------------------

                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    usage_stats = usage

                timings = chunk.get("timings")
                if isinstance(timings, dict):
                    timing_stats = timings

                # ------------------------------------------------
                # Choices
                # ------------------------------------------------

                choices = chunk.get("choices", [])

                if not choices:
                    continue

                choice = choices[0]

                delta = choice.get("delta", {})

                if not isinstance(delta, dict):
                    continue

                # ------------------------------------------------
                # Normal answer
                # ------------------------------------------------

                content = delta.get("content")

                if content:
                    full_answer += content

                    if token_callback:
                        token_callback(content)

                # ------------------------------------------------
                # Reasoning
                # ------------------------------------------------

                reasoning = delta.get(
                    "reasoning_content"
                )

                if reasoning:
                    full_reasoning += reasoning

                    if thinking_callback:
                        thinking_callback(reasoning)

        # --------------------------------------------------------
        # Important fallback
        #
        # Some llama.cpp/Qwen combinations can return reasoning
        # while content is empty. We don't want Boltu to appear
        # completely dead.
        # --------------------------------------------------------

        if not full_answer and full_reasoning:

            fallback = (
                "[The model returned reasoning but no final answer.]\n\n"
                + full_reasoning
            )

            full_answer = fallback

            if token_callback:
                token_callback(fallback)

        # --------------------------------------------------------
        # Store assistant message
        # --------------------------------------------------------

        if full_answer:
            add_assistant_message(full_answer)

        # --------------------------------------------------------
        # Report exact generation statistics
        # --------------------------------------------------------

        if stats_callback:
            stats = {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "generation_seconds": None,
                "tokens_per_second": None,
            }

            if isinstance(usage_stats, dict):
                stats["prompt_tokens"] = usage_stats.get("prompt_tokens")
                stats["completion_tokens"] = usage_stats.get(
                    "completion_tokens"
                )
                stats["total_tokens"] = usage_stats.get("total_tokens")

            if isinstance(timing_stats, dict):
                if timing_stats.get("predicted_ms") is not None:
                    stats["generation_seconds"] = (
                        timing_stats["predicted_ms"] / 1000.0
                    )

                stats["tokens_per_second"] = timing_stats.get(
                    "predicted_per_second"
                )

                # Fallback if usage is unavailable.
                if stats["completion_tokens"] is None:
                    stats["completion_tokens"] = timing_stats.get(
                        "predicted_n"
                    )

            try:
                stats_callback(stats)
            except Exception:
                pass

        return full_answer

    except urllib.error.HTTPError as e:

        try:
            error_body = e.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            error_body = ""

        error = (
            f"Server returned HTTP {e.code}"
        )

        if error_body:
            error += f": {error_body}"

        if error_callback:
            error_callback(error)

        return full_answer

    except urllib.error.URLError as e:

        error = (
            "Could not connect to llama-server: "
            + str(e.reason)
        )

        if error_callback:
            error_callback(error)

        return full_answer

    except Exception as e:

        error = (
            "Unexpected error while generating response: "
            + str(e)
        )

        if error_callback:
            error_callback(error)

        return full_answer


# ============================================================
# INITIALIZATION
# ============================================================

load_config()