import json
import os
from copy import deepcopy
from pathlib import Path
from threading import Lock

import gradio

from facefusion import process_manager, state_manager
from facefusion.face_store import clear_faces
from facefusion.filesystem import is_video
from facefusion.processors.core import load_processor_module
from facefusion.processors.modules.face_swapper.choices import face_swapper_set
from facefusion.uis.components import face_selector, output_options, trim_frame
from facefusion.uis.components.instant_runner import check_export, run_lock
from facefusion.vision import detect_video_fps


GUIDE = {
	'No output': 'Read **Export check** first. Fix the first item it flags. If the check passes and Start still fails, read the message next to Start. Use **Reset swap settings** if you changed several controls.',
	'Wrong person changed': 'Set **Face Selector Mode** to **Reference**. Scrub to a clear frame, then click the intended person in the face gallery. If the swap jumps to someone else, lower **Reference Face Distance** a little.',
	'Looks like the wrong face': 'Turn off **Face Enhancer** for the comparison. Try a sharper source photo with similar lighting and angle. Compare models on the same short section.',
	'Visible edges or covered face': 'Keep **Box** on. Add **Occlusion** if glasses or a hand are painted over. For a jawline seam, move **Face Mask Blur** one step and compare the same frame.',
	'Flicker, slow render or disconnect': 'Test a short section with **Pixel Boost 256×256**, only **Face Swapper**, and **Strict** memory. If CoreML disconnects during a render, select only **CPU** under Execution Providers and retry.',
	'Ready to export': 'Check a head turn and a frame with speech in Preview. Set **Trim Frame** to the range you want to save. Check **Output Path**, then click **Start**.'
}

SUFFIXES = ('_RANGE_SLIDER', '_CHECKBOX_GROUP', '_DROPDOWN', '_SLIDER')
PRESET_PATH = Path(__file__).resolve().parents[3] / '.assets' / 'user_presets.json'
PRESET_LOCK = Lock()


def read_presets():
	try:
		with PRESET_PATH.open(encoding = 'utf-8') as preset_file:
			presets = json.load(preset_file)
		return presets if isinstance(presets, dict) else {}
	except (FileNotFoundError, OSError, ValueError):
		return {}


def write_presets(presets):
	PRESET_PATH.parent.mkdir(parents = True, exist_ok = True)
	temp_path = PRESET_PATH.with_suffix('.tmp')
	try:
		with temp_path.open('w', encoding = 'utf-8') as preset_file:
			json.dump(presets, preset_file, indent = 2, sort_keys = True)
			preset_file.write('\n')
		os.replace(temp_path, PRESET_PATH)
	finally:
		if temp_path.exists():
			temp_path.unlink()


def render_model_preset():
	global PRESET_NAME, PRESET_CHOICE, SAVE_PRESET, LOAD_PRESET, DELETE_PRESET, PRESET_RESULT, REFRESH
	with gradio.Group(elem_id = 'saved-settings'):
		gradio.Markdown('### Saved settings\nName a setup to use it again. Source, target, and output location stay separate.')
		PRESET_NAME = gradio.Textbox(label = 'Setting name', placeholder = 'For example: Strong portrait', max_lines = 1)
		PRESET_CHOICE = gradio.Dropdown(choices = sorted(read_presets()), label = 'Saved settings', interactive = True)
		with gradio.Row():
			SAVE_PRESET = gradio.Button('Save settings', variant = 'primary', size = 'sm')
			LOAD_PRESET = gradio.Button('Apply selected', size = 'sm')
			DELETE_PRESET = gradio.Button('Delete selected', size = 'sm')
		PRESET_RESULT = gradio.Markdown(elem_id = 'saved-settings-result')
		REFRESH = gradio.Timer(2)


def render_recovery():
	global RESET, RESET_RESULT, EXPORT_CHECK, CHANGES
	EXPORT_CHECK = gradio.Markdown(elem_id = 'export-check')
	with gradio.Accordion('Troubleshoot or reset', open = False):
		RESET = gradio.Button('Reset swap settings', size = 'sm')
		RESET_RESULT = gradio.Markdown('Restores the initial controls. Keeps your source, target and output location.')
		CHANGES = gradio.Markdown()


def render_guide():
	topic = gradio.Dropdown(list(GUIDE), value = 'No output', label = 'What needs fixing?', interactive = True)
	instructions = gradio.Markdown(GUIDE['No output'])
	topic.change(GUIDE.get, inputs = topic, outputs = instructions, queue = False,
		api_name = 'facefusion_guide_topic', show_api = False)


def listen(modules):
	state = state_manager.get_state()
	bindings = []
	for module in modules:
		for name, control in vars(module).items():
			for suffix in SUFFIXES:
				if name.endswith(suffix) and isinstance(control, (gradio.Dropdown, gradio.Slider, gradio.CheckboxGroup)):
					key = name[:-len(suffix)].lower()
					if key in state and key != 'output_video_fps':
						bindings.append((key, control, deepcopy(state[key]), deepcopy(control.value)))
					break

	paddings = [face_mask_control(modules, side) for side in ('TOP', 'RIGHT', 'BOTTOM', 'LEFT')]
	special = [
		('face_mask_padding', 'Mask padding'),
		('face_selector_age_start', 'Minimum face age'),
		('face_selector_age_end', 'Maximum face age'),
		('trim_frame_start', 'Trim start'),
		('trim_frame_end', 'Trim end'),
		('output_video_fps', 'Output FPS')
	]
	original = {key: deepcopy(state.get(key)) for key, _ in special}
	age = face_selector.FACE_SELECTOR_AGE_RANGE_SLIDER
	age_default = deepcopy(age.value)
	trim = trim_frame.TRIM_FRAME_RANGE_SLIDER
	fps = output_options.OUTPUT_VIDEO_FPS_SLIDER
	controls = [control for _, control, _, _ in bindings]
	apply_outputs = [*controls, *paddings, age, trim, fps, PRESET_RESULT]

	def save(name):
		name = (name or '').strip()
		if not name:
			return gradio.skip(), 'Enter a setting name first.'
		if len(name) > 80:
			return gradio.skip(), 'Use a name of 80 characters or fewer.'
		current = state_manager.get_state()
		values = {key: deepcopy(current.get(key)) for key, _, _, _ in bindings}
		values.update({key: deepcopy(current.get(key)) for key, _ in special})
		with PRESET_LOCK:
			presets = read_presets()
			presets[name] = values
			write_presets(presets)
		return gradio.update(choices = sorted(presets), value = name), f'**Saved “{name}”** ({len(values)} settings). Saving the same name again updates it.'

	def load(name):
		skips = [gradio.skip()] * (len(apply_outputs) - 1)
		if not name:
			return skips + ['Select saved settings first.']
		if not process_manager.is_pending() or not run_lock.acquire(blocking = False):
			return skips + ['Wait for the current render to finish, then apply again.']
		try:
			with PRESET_LOCK:
				values = read_presets().get(name)
			if not isinstance(values, dict):
				return skips + ['That saved setting was not found.']
			model = values.get('face_swapper_model')
			previous_model = state_manager.get_item('face_swapper_model')
			if model and model != previous_model:
				state_manager.set_item('face_swapper_model', model)
				model_module = load_processor_module('face_swapper')
				model_module.clear_inference_pool()
				if not model_module.pre_check():
					state_manager.set_item('face_swapper_model', previous_model)
					return skips + [f'Could not load model **{model}**. Other controls were kept.']
			updates = []
			for key, control, _, _ in bindings:
				if key not in values:
					updates.append(gradio.skip())
					continue
				value = deepcopy(values[key])
				state_manager.set_item(key, value)
				options = {'value': value}
				if key == 'face_swapper_pixel_boost' and model in face_swapper_set:
					options['choices'] = face_swapper_set[model]
				updates.append(gradio.update(**options))
			padding = values.get('face_mask_padding', original['face_mask_padding'])
			state_manager.set_item('face_mask_padding', padding)
			for key in ('face_selector_age_start', 'face_selector_age_end', 'trim_frame_start', 'trim_frame_end'):
				if key in values:
					state_manager.set_item(key, values[key])
			fps_value = values.get('output_video_fps')
			fps_update = gradio.skip()
			video_target = is_video(state_manager.get_item('target_path'))
			if fps_value is not None and video_target:
				state_manager.set_item('output_video_fps', fps_value)
				fps_update = gradio.update(value = fps_value)
			age_start = values.get('face_selector_age_start') or age_default[0]
			age_end = values.get('face_selector_age_end') or age_default[1]
			trim_update = gradio.skip()
			if video_target:
				trim_update = gradio.update(value = (values.get('trim_frame_start') or 0,
					values.get('trim_frame_end') or trim.maximum))
			clear_faces()
			return [*updates, *(gradio.update(value = value) for value in padding),
				gradio.update(value = (age_start, age_end)), trim_update, fps_update,
				f'**Applied “{name}”.** Check Preview before exporting.']
		finally:
			run_lock.release()

	def delete(name):
		if not name:
			return gradio.skip(), 'Select saved settings to delete.'
		with PRESET_LOCK:
			presets = read_presets()
			if name not in presets:
				return gradio.update(choices = sorted(presets), value = None), 'That saved setting was not found.'
			del presets[name]
			write_presets(presets)
		return gradio.update(choices = sorted(presets), value = None), f'Deleted “{name}”. Current controls were kept.'

	def reset():
		if run_lock.locked() or not process_manager.is_pending():
			return [gradio.skip()] * (len(bindings) + 7) + ['Wait for the current job to finish, then try again.']
		updates = []
		for key, control, default, value in bindings:
			state_manager.set_item(key, deepcopy(default))
			updates.append(gradio.update(value = deepcopy(value)))
		for key, value in original.items():
			state_manager.set_item(key, deepcopy(value))
		clear_faces()
		target = state_manager.get_item('target_path')
		fps_update = gradio.skip()
		if is_video(target):
			target_fps = detect_video_fps(target)
			state_manager.set_item('output_video_fps', target_fps)
			fps_update = gradio.update(value = target_fps)
		return updates + [
			*(gradio.update(value = value) for value in original['face_mask_padding']),
			gradio.update(value = age_default), trim_frame.remote_update(), fps_update,
			'Restored the initial swap settings. Check Preview before exporting.'
		]

	def inspect():
		current = state_manager.get_state()
		error = check_export(current)
		status = f'**Export check:** {error}' if error else '**Export check:** Inputs and output path pass the basic checks.'
		if current.get('ui_workflow') != 'instant_runner':
			status += ' Choose **Instant Runner** to render immediately.'
		changes = []
		for key, control, baseline, _ in bindings:
			if current.get(key) != baseline:
				changes.append(format_change(control.label, baseline, current.get(key)))
		for key, label in special:
			if current.get(key) != original[key]:
				changes.append(format_change(label, original[key], current.get(key)))
		return status, '\n'.join(changes) or 'No tracked settings differ from the initial controls.'

	EXPORT_CHECK.value, CHANGES.value = inspect()
	REFRESH.tick(inspect, outputs = [EXPORT_CHECK, CHANGES], queue = False,
		api_name = 'export_check', show_api = False)
	SAVE_PRESET.click(save, inputs = PRESET_NAME, outputs = [PRESET_CHOICE, PRESET_RESULT],
		api_name = 'save_user_preset', show_api = False)
	LOAD_PRESET.click(load, inputs = PRESET_CHOICE, outputs = apply_outputs,
		api_name = 'load_user_preset', show_api = False)
	DELETE_PRESET.click(delete, inputs = PRESET_CHOICE, outputs = [PRESET_CHOICE, PRESET_RESULT],
		api_name = 'delete_user_preset', show_api = False)
	RESET.click(reset, outputs = [*controls, *paddings, age, trim, fps, RESET_RESULT],
		api_name = 'reset_swap_settings', show_api = False)


def face_mask_control(modules, side):
	return next(getattr(module, 'FACE_MASK_PADDING_' + side + '_SLIDER') for module in modules
		if hasattr(module, 'FACE_MASK_PADDING_' + side + '_SLIDER'))


def format_change(label, before, after):
	return f'- **{label.title()}:** {display_value(before)} → {display_value(after)}'


def display_value(value):
	if isinstance(value, (list, tuple)):
		return ', '.join(map(str, value)) or 'None'
	return 'Default' if value is None else str(value)
