import logging
import os
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Optional, Tuple

import gradio

from facefusion import logger, process_manager, state_manager, translator
from facefusion.args import collect_step_args
from facefusion.core import process_step
from facefusion.filesystem import has_audio, has_image, is_directory, is_image, is_video, same_file_extension
from facefusion.jobs import job_helper, job_manager, job_runner, job_store
from facefusion.temp_helper import clear_temp_directory
from facefusion.types import Args, UiWorkflow
from facefusion.uis.core import get_ui_component
from facefusion.uis.ui_helper import suggest_output_path

INSTANT_RUNNER_WRAPPER : Optional[gradio.Row] = None
INSTANT_RUNNER_START_BUTTON : Optional[gradio.Button] = None
INSTANT_RUNNER_STOP_BUTTON : Optional[gradio.Button] = None
INSTANT_RUNNER_CLEAR_BUTTON : Optional[gradio.Button] = None
RUN_RESULT : Optional[gradio.Markdown] = None
run_lock = Lock()


def render() -> None:
	global INSTANT_RUNNER_WRAPPER
	global INSTANT_RUNNER_START_BUTTON
	global INSTANT_RUNNER_STOP_BUTTON
	global INSTANT_RUNNER_CLEAR_BUTTON
	global RUN_RESULT

	if job_manager.init_jobs(state_manager.get_item('jobs_path')):
		is_instant_runner = state_manager.get_item('ui_workflow') == 'instant_runner'

		with gradio.Row(visible = is_instant_runner) as INSTANT_RUNNER_WRAPPER:
			INSTANT_RUNNER_START_BUTTON = gradio.Button(
				value = translator.get('uis.start_button'),
				variant = 'primary',
				size = 'sm'
			)
			INSTANT_RUNNER_STOP_BUTTON = gradio.Button(
				value = translator.get('uis.stop_button'),
				variant = 'primary',
				size = 'sm',
				visible = False
			)
			INSTANT_RUNNER_CLEAR_BUTTON = gradio.Button(
				value = translator.get('uis.clear_button'),
				size = 'sm'
			)
		RUN_RESULT = gradio.Markdown()


def listen() -> None:
	output_image = get_ui_component('output_image')
	output_video = get_ui_component('output_video')
	ui_workflow_dropdown = get_ui_component('ui_workflow_dropdown')

	if output_image and output_video:
		INSTANT_RUNNER_START_BUTTON.click(run, outputs = [ INSTANT_RUNNER_START_BUTTON, INSTANT_RUNNER_STOP_BUTTON, output_image, output_video, RUN_RESULT ])
		INSTANT_RUNNER_STOP_BUTTON.click(stop, queue = False)
		INSTANT_RUNNER_CLEAR_BUTTON.click(clear, outputs = [ output_image, output_video ])
	if ui_workflow_dropdown:
		ui_workflow_dropdown.change(remote_update, inputs = ui_workflow_dropdown, outputs = INSTANT_RUNNER_WRAPPER)


def remote_update(ui_workflow : UiWorkflow) -> gradio.Row:
	is_instant_runner = ui_workflow == 'instant_runner'

	return gradio.Row(visible = is_instant_runner)


def check_export(args):
	target = args.get('target_path')
	if not (is_image(target) or is_video(target)):
		return 'Add a target photo or video.'
	processors = args.get('processors') or []
	if not processors:
		return 'Select at least one processor. For a face swap, enable Face Swapper.'
	if 'face_swapper' in processors and not has_image(args.get('source_paths')):
		return 'Add a source photo for Face Swapper.'
	if 'face_swapper' in processors and not args.get('face_mask_types'):
		return 'Enable Box under Face Mask Types, or reset the swap settings.'
	if 'lip_syncer' in processors and not has_audio(args.get('source_paths')):
		return 'Add source audio for Lip Syncer, or turn Lip Syncer off.'
	start, end = args.get('trim_frame_start') or 0, args.get('trim_frame_end')
	if is_video(target) and end is not None and end <= start:
		return 'Expand Trim Frame so the end is after the start.'
	destination = args.get('output_path')
	if not destination:
		return 'Choose an output folder, such as Documents.'
	if is_directory(destination):
		if not os.access(destination, os.W_OK):
			return 'Choose an output folder you can write to.'
	else:
		folder = Path(destination).parent
		if not folder.is_dir() or not os.access(folder, os.W_OK):
			return 'The output folder is missing or unwritable. Choose an existing folder.'
		if not same_file_extension(destination, target):
			return 'Use an output folder, or give the output file the same extension as the target.'
		inputs = [target, *(args.get('source_paths') or [])]
		if any(Path(destination).resolve() == Path(path).resolve() for path in inputs):
			return 'Choose a different output location to protect your original files.'
	return None


class RenderErrors(logging.Handler):
	def __init__(self):
		super().__init__(logging.ERROR)
		self.messages = []

	def emit(self, record):
		self.messages.append(record.getMessage())


def run():
	idle = (gradio.update(visible = True), gradio.update(visible = False))
	keep_output = (gradio.skip(), gradio.skip())
	if not run_lock.acquire(blocking = False):
		yield gradio.skip(), gradio.skip(), *keep_output, 'A render is already running.'
		return
	try:
		step_args = collect_step_args()
		error = check_export(step_args)
		if error:
			yield *idle, *keep_output, f'**Export did not start.** {error}'
			return
		output_path = step_args.get('output_path')
		if is_directory(output_path):
			step_args['output_path'] = suggest_output_path(output_path, step_args['target_path'])
		destination = step_args['output_path']
		yield gradio.update(visible = False), gradio.update(visible = True), *keep_output, '**Rendering…** See Terminal for progress.'
		errors = RenderErrors()
		app_logger = logger.get_package_logger()
		app_logger.addHandler(errors)
		try:
			success = job_manager.init_jobs(state_manager.get_item('jobs_path')) and create_and_run_job(step_args)
		except Exception as error:
			app_logger.error('%s', error)
			success = False
		finally:
			app_logger.removeHandler(errors)
			state_manager.set_item('output_path', output_path)
		if success and is_image(destination):
			yield *idle, gradio.update(value = destination, visible = True), gradio.update(value = None, visible = False), f'**Saved:** {destination}'
		elif success and is_video(destination):
			yield *idle, gradio.update(value = None, visible = False), gradio.update(value = destination, visible = True), f'**Saved:** {destination}'
		else:
			detail = '\n\n'.join(dict.fromkeys(errors.messages[-3:]))
			yield *idle, *keep_output, '**No new output was saved.** ' + (detail or 'The job did not finish. Check Terminal for details, or reset the swap settings and retry a short clip.')
	finally:
		run_lock.release()


def create_and_run_job(step_args : Args) -> bool:
	job_id = job_helper.suggest_job_id('ui')

	for key in job_store.get_job_keys():
		state_manager.sync_item(key) #type:ignore[arg-type]

	return job_manager.create_job(job_id) and job_manager.add_step(job_id, step_args) and job_manager.submit_job(job_id) and job_runner.run_job(job_id, process_step)


def stop() -> None:
	if process_manager.is_processing():
		process_manager.stop()


def clear() -> Tuple[gradio.Image, gradio.Video]:
	while process_manager.is_processing():
		sleep(0.5)
	if state_manager.get_item('target_path'):
		clear_temp_directory(state_manager.get_item('target_path'))
	return gradio.Image(value = None), gradio.Video(value = None)
