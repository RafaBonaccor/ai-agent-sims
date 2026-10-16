#!/usr/bin/env python3
import argparse
import copy
import os
import random
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
import venv
import zipfile
from pathlib import Path


def _script_entry_path() -> Path:
    if "__file__" in globals():
        return Path(__file__).resolve()
    argv0 = str(sys.argv[0] or "").strip()
    if argv0 and argv0 not in {"-c", "-m", "ipykernel_launcher", "ipykernel_launcher.py"}:
        return Path(argv0).expanduser().resolve()
    fallback = Path.cwd() / "catalog_server_vast.py"
    return fallback.resolve()


def ensure_runtime() -> None:
    if os.environ.get("CATALOG_BOOTSTRAPPED") == "1":
        return
    try:
        import requests  # noqa: F401
        import flask  # noqa: F401
        return
    except Exception:
        pass

    runtime_dir = Path(os.environ.get("CATALOG_RUNTIME_DIR", "/workspace/catalog-venv")).expanduser().resolve()
    python_bin = runtime_dir / "bin" / "python"
    pip_bin = runtime_dir / "bin" / "pip"

    if not python_bin.exists():
        print(f"[BOOTSTRAP] creating venv at {runtime_dir}", flush=True)
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=True).create(str(runtime_dir))

    print("[BOOTSTRAP] installing flask requests into local venv", flush=True)
    subprocess.check_call([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(pip_bin), "install", "flask", "requests"])

    env = dict(os.environ)
    env["CATALOG_BOOTSTRAPPED"] = "1"
    os.execve(str(python_bin), [str(python_bin), str(_script_entry_path()), *sys.argv[1:]], env)


ensure_runtime()

import requests
from flask import Flask, jsonify, render_template_string, request, send_file

MODELS = {
    "vae": [
        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
        "https://huggingface.co/black-forest-labs/FLUX.2-small-decoder/resolve/main/full_encoder_small_decoder.safetensors",
    ],
    "text_encoders": [
        "https://huggingface.co/chatpig/encoder/resolve/main/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors",
        "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors",
    ],
    "diffusion_models": [
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        "https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9b-fp8/resolve/main/flux-2-klein-base-9b-fp8.safetensors",
    ],
    "loras": [
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
    ],
}

TEMPLATES = {
    "ecommerce_white": {
        "variations": 2,
        "prompt": "Use reference image 1 as the authoritative jewelry product reference. Create a professional e-commerce photograph of the exact same jewelry on a seamless white studio background. Centered, fully visible, soft studio lighting, realistic reflections and subtle shadow. Preserve geometry, proportions, metal color, stones, engravings, chain, clasp and all details exactly.",
    },
    "model_wearing": {
        "variations": 2,
        "prompt": "Use reference image 1 as the authoritative jewelry product reference. Place the exact jewelry naturally on an elegant female model with anatomically correct placement. Premium jewelry photography, realistic skin, scale, lighting and reflections. Preserve the jewelry exactly.",
    },
    "model_reference": {
        "variations": 2,
        "requires_reference_2": True,
        "prompt": "Reference image 1 defines the exact jewelry. Reference image 2 defines the model identity, appearance and style. Place the jewelry from reference image 1 naturally on the model from reference image 2. Preserve both faithfully.",
    },
    "hand": {
        "variations": 2,
        "prompt": "Show the exact jewelry from reference image 1 resting elegantly on a woman’s open hands. Keep all product details visible. Premium jewelry photography, realistic skin, soft natural lighting, shallow depth of field.",
    },
    "holding_jewelry": {
        "variations": 2,
        "prompt": "Create an elegant close-up of a woman’s hand gently holding the exact jewelry from reference image 1. Keep the jewelry unchanged and clearly visible.",
    },
    "jewelry_stand": {
        "variations": 2,
        "prompt": "Place the exact jewelry from reference image 1 on a minimal premium jewelry display stand. Neutral luxury background, studio lighting, realistic shadows and reflections.",
    },
    "luxury_fabric": {
        "variations": 2,
        "prompt": "Place the exact jewelry from reference image 1 naturally on luxurious soft fabric with subtle folds. Premium editorial jewelry photography, shallow depth of field, realistic reflections.",
    },
    "marble": {
        "variations": 2,
        "prompt": "Place the exact jewelry from reference image 1 on elegant light marble. Minimal premium composition, realistic studio lighting, soft shadows, subtle reflections.",
    },
    "black_luxury": {
        "variations": 2,
        "prompt": "Create a high-end product photograph of the exact jewelry from reference image 1 on a dark elegant background with controlled dramatic lighting.",
    },
    "macro": {
        "variations": 2,
        "prompt": "Create an extreme close-up macro photograph of the exact jewelry from reference image 1, emphasizing craftsmanship, metal texture, gemstones, engravings and fine details.",
    },
    "capri": {
        "variations": 2,
        "prompt": "Create a luxury Mediterranean jewelry campaign photograph with the exact jewelry from reference image 1 in Capri, Italy, blue sea, elegant sunlight and refined Italian summer atmosphere.",
    },
    "sunset": {
        "variations": 2,
        "prompt": "Create an elegant luxury jewelry campaign during golden hour at sunset using the exact jewelry from reference image 1. Warm natural sunlight and realistic commercial photography.",
    },
    "gift": {
        "variations": 2,
        "prompt": "Create an elegant gifting-oriented jewelry advertisement using the exact jewelry from reference image 1 in a refined luxury setting.",
    },
    "social_ad": {
        "variations": 3,
        "prompt": "Create a visually striking premium social-media advertisement using the exact jewelry from reference image 1. Strong product focus, modern luxury composition, realistic commercial photography. No text or logos.",
    },
}

WORKFLOW_SINGLE = {
    "1000": {"class_type": "LoadImage", "inputs": {"image": "comfy_logo_blue.png"}},
    "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "62": {"class_type": "Flux2Scheduler", "inputs": {"steps": 20, "width": ["100", 0], "height": ["100", 1]}},
    "63": {"class_type": "CFGGuider", "inputs": {"cfg": 5, "model": ["70", 0], "positive": ["124", 0], "negative": ["122", 0]}},
    "64": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["73", 0], "guider": ["63", 0], "sampler": ["61", 0], "sigmas": ["62", 0], "latent_image": ["66", 0]}},
    "65": {"class_type": "VAEDecode", "inputs": {"samples": ["64", 0], "vae": ["72", 0]}},
    "73": {"class_type": "RandomNoise", "inputs": {"noise_seed": 192774551144773}},
    "70": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-base-9b-fp8.safetensors", "weight_dtype": "default"}},
    "71": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2", "device": "default"}},
    "74": {"class_type": "CLIPTextEncode", "inputs": {"text": "Change the camera angle to a first-person driver's perspective looking through the steering wheel at the dashboard and windshield, maintaining the same white minimalist interior style and lighting", "clip": ["71", 0]}},
    "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["71", 0]}},
    "72": {"class_type": "VAELoader", "inputs": {"vae_name": "full_encoder_small_decoder.safetensors"}},
    "66": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["100", 0], "height": ["100", 1], "batch_size": 1}},
    "80": {"class_type": "ImageScaleToTotalPixels", "inputs": {"upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 1, "image": ["1000", 0]}},
    "100": {"class_type": "GetImageSize", "inputs": {"image": ["80", 0]}},
    "122": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["67", 0], "latent": ["123", 0]}},
    "123": {"class_type": "VAEEncode", "inputs": {"pixels": ["80", 0], "vae": ["72", 0]}},
    "124": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["74", 0], "latent": ["123", 0]}},
    "1001": {"class_type": "SaveImage", "inputs": {"images": ["65", 0], "filename_prefix": "catalog/output"}},
}

WORKFLOW_DOUBLE = {
    "2000": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
    "2001": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}},
    "102": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "103": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["105", 0], "guider": ["114", 0], "sampler": ["102", 0], "sigmas": ["115", 0], "latent_image": ["109", 0]}},
    "104": {"class_type": "VAEDecode", "inputs": {"samples": ["103", 0], "vae": ["107", 0]}},
    "105": {"class_type": "RandomNoise", "inputs": {"noise_seed": 123456789}},
    "106": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-base-9b-fp8.safetensors", "weight_dtype": "default"}},
    "107": {"class_type": "VAELoader", "inputs": {"vae_name": "full_encoder_small_decoder.safetensors"}},
    "108": {"class_type": "GetImageSize", "inputs": {"image": ["110", 0]}},
    "109": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["108", 0], "height": ["108", 1], "batch_size": 1}},
    "110": {"class_type": "ImageScaleToTotalPixels", "inputs": {"upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 1, "image": ["2000", 0]}},
    "85": {"class_type": "ImageScaleToTotalPixels", "inputs": {"upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 1, "image": ["2001", 0]}},
    "111": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2", "device": "default"}},
    "113": {"class_type": "CLIPTextEncode", "inputs": {"text": "Preserve the exact product from reference image 1.", "clip": ["111", 0]}},
    "87": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["111", 0]}},
    "114": {"class_type": "CFGGuider", "inputs": {"cfg": 5, "model": ["106", 0], "positive": ["130", 0], "negative": ["128", 0]}},
    "115": {"class_type": "Flux2Scheduler", "inputs": {"steps": 20, "width": ["108", 0], "height": ["108", 1]}},
    "125": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["87", 0], "latent": ["126", 0]}},
    "126": {"class_type": "VAEEncode", "inputs": {"pixels": ["110", 0], "vae": ["107", 0]}},
    "127": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["113", 0], "latent": ["126", 0]}},
    "128": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["125", 0], "latent": ["129", 0]}},
    "129": {"class_type": "VAEEncode", "inputs": {"pixels": ["85", 0], "vae": ["107", 0]}},
    "130": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["127", 0], "latent": ["129", 0]}},
    "2999": {"class_type": "SaveImage", "inputs": {"images": ["104", 0], "filename_prefix": "catalog/output"}},
}

app = Flask(__name__)
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
COMFYUI_PATH = Path("/workspace/ComfyUI")
COMFY_URL = "http://127.0.0.1:8188"
SERVER_PASSWORD = ""
JOBS_DIR = Path("/workspace/catalog_jobs")

HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Jewelry Catalog AI</title><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#111;color:#eee;margin:0}.wrap{max-width:960px;margin:40px auto;padding:0 20px}.card{background:#1b1b1b;border:1px solid #333;border-radius:16px;padding:24px;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.template{background:#141414;border:1px solid #333;padding:10px;border-radius:10px}label{display:block;font-weight:600;margin:14px 0 7px}input[type=text],input[type=password],input[type=number],input[type=file]{width:100%;box-sizing:border-box;padding:12px;background:#111;color:#eee;border:1px solid #444;border-radius:9px}button{padding:13px 20px;font-size:16px;font-weight:700;border:0;border-radius:10px;cursor:pointer}.progress{height:14px;background:#333;border-radius:20px;overflow:hidden}.bar{height:100%;width:0;background:#ddd}.small{color:#aaa;font-size:13px}a.download{display:inline-block;padding:12px 16px;background:#eee;color:#111;text-decoration:none;border-radius:9px;font-weight:700}#statusBox{display:none}</style></head><body><div class='wrap'><div class='card'><h1>Jewelry Catalog AI</h1><form id='f'><label>Password</label><input type='password' name='password' required><label>Product</label><input type='text' name='product' required><label>Product reference</label><input type='file' name='image1' accept='image/*' required><label>Second reference (optional model/style)</label><input type='file' name='image2' accept='image/*'><label>Variations override</label><input type='number' name='variations' min='1' max='10'><label>Templates</label><div class='grid'>{% for n,t in templates.items() %}<div class='template'><label style='margin:0'><input type='checkbox' name='templates' value='{{n}}' checked> {{n.replace('_',' ').title()}}</label><div class='small'>{{t.get('variations',1)}} default{% if t.get('requires_reference_2') %} · needs ref 2{% endif %}</div></div>{% endfor %}</div><br><button>Generate catalog</button></form></div><div class='card' id='statusBox'><h2>Generation</h2><div id='statusText'>Starting…</div><br><div class='progress'><div class='bar' id='bar'></div></div><p class='small' id='detail'></p><div id='download'></div></div></div><script>const f=document.getElementById('f'),b=document.getElementById('statusBox'),bar=document.getElementById('bar'),txt=document.getElementById('statusText'),d=document.getElementById('detail'),dl=document.getElementById('download');f.addEventListener('submit',async e=>{e.preventDefault();b.style.display='block';const fd=new FormData(f);const r=await fetch('/generate',{method:'POST',body:fd});const j=await r.json();if(!r.ok){txt.textContent='Error: '+(j.error||'request failed');return}poll(j.job_id,fd.get('password'))});async function poll(id,pw){const r=await fetch('/status/'+id+'?password='+encodeURIComponent(pw));const j=await r.json();if(!r.ok){txt.textContent='Error: '+(j.error||'status failed');return}txt.textContent=j.status;let pct=j.total?Math.round(j.completed/j.total*100):0;bar.style.width=pct+'%';d.textContent=j.completed+' / '+j.total+' complete';if(j.state==='done'){bar.style.width='100%';dl.innerHTML='<a class="download" href="/download/'+id+'?password='+encodeURIComponent(pw)+'">Download ZIP</a>';return}if(j.state==='error'){txt.textContent='Error: '+j.error;return}setTimeout(()=>poll(id,pw),2000)}</script></body></html>"""


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_") or "product"


def auth(password: str) -> bool:
    return bool(password) and password == SERVER_PASSWORD


def openp(host: str, port: int) -> bool:
    try:
        sock = socket.create_connection((host, port), 0.5)
        sock.close()
        return True
    except OSError:
        return False


def dl(url: str, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    path = target_dir / name
    if path.exists() and path.stat().st_size > 1024:
        print("[SKIP]", path, flush=True)
        return
    print("[DOWNLOAD]", name, flush=True)
    subprocess.run(["wget", "-c", "--show-progress", "-O", str(path), url], check=True)


def setup_models() -> None:
    for model_type, urls in MODELS.items():
        for url in urls:
            try:
                dl(url, COMFYUI_PATH / "models" / model_type)
            except Exception as exc:
                print("[WARN]", url, exc, flush=True)


def start_comfy() -> None:
    if openp("127.0.0.1", 8188):
        print("[OK] ComfyUI already running", flush=True)
        return
    main = COMFYUI_PATH / "main.py"
    if not main.exists():
        raise RuntimeError("ComfyUI not found at " + str(COMFYUI_PATH))
    log = open(COMFYUI_PATH / "catalog_comfyui.log", "a", buffering=1)
    proc = subprocess.Popen(
        [sys.executable, str(main), "--listen", "127.0.0.1", "--port", "8188"],
        cwd=str(COMFYUI_PATH),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    end = time.time() + 120
    while time.time() < end:
        if openp("127.0.0.1", 8188):
            print("[OK] ComfyUI ready", flush=True)
            return
        if proc.poll() is not None:
            raise RuntimeError("ComfyUI exited; see catalog_comfyui.log")
        time.sleep(2)
    raise RuntimeError("ComfyUI start timeout")


def upload(path: str) -> str:
    with open(path, "rb") as file_handle:
        response = requests.post(
            COMFY_URL + "/upload/image",
            files={"image": (Path(path).name, file_handle, "application/octet-stream")},
            data={"overwrite": "true", "type": "input", "subfolder": "catalog_inputs"},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    return (payload.get("subfolder", "") + "/" + payload["name"]).strip("/")


def nodes(workflow: dict) -> dict:
    out = {"prompt": [], "images": [], "save": [], "seed": []}
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if class_type == "CLIPTextEncode" and "text" in inputs:
            out["prompt"].append(str(node_id))
        if class_type == "LoadImage" and "image" in inputs:
            out["images"].append(str(node_id))
        if class_type == "SaveImage":
            out["save"].append(str(node_id))
        if class_type == "RandomNoise" and "noise_seed" in inputs:
            out["seed"].append(str(node_id))
    return out


def queue(workflow: dict) -> str:
    response = requests.post(COMFY_URL + "/prompt", json={"prompt": workflow}, timeout=120)
    if not response.ok:
        raise RuntimeError(response.text[:1500])
    return response.json()["prompt_id"]


def wait(prompt_id: str, timeout: int = 1800) -> list:
    end = time.time() + timeout
    while time.time() < end:
        history = requests.get(COMFY_URL + "/history/" + prompt_id, timeout=60).json().get(prompt_id)
        if history:
            if history.get("status", {}).get("status_str") == "error":
                raise RuntimeError("ComfyUI job failed")
            images = []
            for output in history.get("outputs", {}).values():
                images.extend(output.get("images", []))
            if images:
                return images
        time.sleep(2)
    raise TimeoutError(prompt_id)


def fetch(image: dict) -> bytes:
    response = requests.get(
        COMFY_URL + "/view",
        params={
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.content


def build(template_name: str, template: dict, ref1: str, ref2: str | None, product_slug: str, index: int) -> dict:
    base = WORKFLOW_DOUBLE if ref2 and template.get("requires_reference_2") and WORKFLOW_DOUBLE else WORKFLOW_SINGLE
    workflow = copy.deepcopy(base)
    refs = nodes(workflow)
    workflow[refs["prompt"][0]]["inputs"]["text"] = template["prompt"]
    workflow[refs["images"][0]]["inputs"]["image"] = ref1
    if ref2 and len(refs["images"]) > 1:
        workflow[refs["images"][1]]["inputs"]["image"] = ref2
    if refs["seed"]:
        workflow[refs["seed"][0]]["inputs"]["noise_seed"] = random.randint(1, 2**63 - 1)
    workflow[refs["save"][0]]["inputs"]["filename_prefix"] = f"catalog/{product_slug}/{template_name}/{template_name}_{product_slug}_{index:02d}"
    return workflow


def worker(job_id: str, product: str, p1: str, p2: str | None, selected: list[str], override_variations: int | None) -> None:
    job_dir = JOBS_DIR / job_id
    results_dir = job_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    try:
        with LOCK:
            JOBS[job_id].update(state="running", status="Uploading references")
        ref1 = upload(p1)
        ref2 = upload(p2) if p2 else None
        product_slug = slug(product)
        queued = []
        for name in selected:
            if name not in TEMPLATES:
                continue
            template = TEMPLATES[name]
            if template.get("requires_reference_2") and not ref2:
                continue
            total_variations = int(override_variations or template.get("variations", 1))
            for i in range(1, total_variations + 1):
                queued.append((name, template, i))
        with LOCK:
            JOBS[job_id].update(total=len(queued), status=f"Queueing {len(queued)} generations")
        jobs = [(name, i, queue(build(name, template, ref1, ref2, product_slug, i))) for name, template, i in queued]
        for name, i, prompt_id in jobs:
            with LOCK:
                JOBS[job_id]["status"] = f"Generating {name} {i}"
            images = wait(prompt_id)
            for k, image in enumerate(images, 1):
                ext = Path(image["filename"]).suffix or ".png"
                (results_dir / f"{name}_{i:02d}_{k:02d}{ext}").write_bytes(fetch(image))
            with LOCK:
                JOBS[job_id]["completed"] += 1
        zip_path = job_dir / f"{product_slug}_catalog.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(results_dir.iterdir()):
                archive.write(file_path, arcname=file_path.name)
        with LOCK:
            JOBS[job_id].update(state="done", status="Completed", zip=str(zip_path))
    except Exception as exc:
        with LOCK:
            JOBS[job_id].update(state="error", status="Failed", error=str(exc))


@app.get("/")
def index():
    return render_template_string(HTML, templates=TEMPLATES)


@app.post("/generate")
def gen():
    password = request.form.get("password", "")
    if not auth(password):
        return jsonify({"error": "Invalid password"}), 401
    product = request.form.get("product", "").strip()
    image1 = request.files.get("image1")
    image2 = request.files.get("image2")
    selected = request.form.getlist("templates")
    if not product or not image1 or not selected:
        return jsonify({"error": "Missing product/image/templates"}), 400
    raw_variations = request.form.get("variations", "").strip()
    override_variations = max(1, min(10, int(raw_variations))) if raw_variations else None
    job_id = uuid.uuid4().hex[:12]
    upload_dir = JOBS_DIR / job_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    p1 = upload_dir / ("reference1" + (Path(image1.filename).suffix or ".png"))
    image1.save(p1)
    p2 = None
    if image2 and image2.filename:
        p2 = upload_dir / ("reference2" + (Path(image2.filename).suffix or ".png"))
        image2.save(p2)
    with LOCK:
        JOBS[job_id] = {
            "state": "queued",
            "status": "Queued",
            "completed": 0,
            "total": 0,
            "error": None,
            "zip": None,
        }
    threading.Thread(
        target=worker,
        args=(job_id, product, str(p1), str(p2) if p2 else None, selected, override_variations),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id})


@app.get("/status/<job_id>")
def status(job_id: str):
    if not auth(request.args.get("password", "")):
        return jsonify({"error": "Invalid password"}), 401
    with LOCK:
        job = JOBS.get(job_id)
        return jsonify(job) if job else (jsonify({"error": "Job not found"}), 404)


@app.get("/download/<job_id>")
def download(job_id: str):
    if not auth(request.args.get("password", "")):
        return jsonify({"error": "Invalid password"}), 401
    with LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("state") != "done":
            return jsonify({"error": "ZIP not ready"}), 404
        path = job["zip"]
    return send_file(path, as_attachment=True)


@app.get("/health")
def health():
    return jsonify({"server": "ok", "comfyui": openp("127.0.0.1", 8188)})


def main():
    global COMFYUI_PATH, SERVER_PASSWORD, JOBS_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui", default="/workspace/ComfyUI")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--password", default=os.environ.get("CATALOG_PASSWORD", ""))
    parser.add_argument("--skip-model-downloads", action="store_true")
    parser.add_argument("--no-start-comfyui", action="store_true")
    args = parser.parse_args()

    COMFYUI_PATH = Path(args.comfyui).resolve()
    SERVER_PASSWORD = args.password
    JOBS_DIR = COMFYUI_PATH.parent / "catalog_jobs"
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    if not SERVER_PASSWORD:
        raise RuntimeError("Missing password. Pass --password or set CATALOG_PASSWORD.")

    print("Catalog jobs dir:", JOBS_DIR, flush=True)

    if not args.skip_model_downloads:
        setup_models()
    if not args.no_start_comfyui:
        start_comfy()

    print(f"Web UI on port {args.port}; recommended SSH tunnel: ssh -N -L {args.port}:localhost:{args.port} -p SSH_PORT root@VAST_IP", flush=True)
    app.run(host="0.0.0.0", port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
