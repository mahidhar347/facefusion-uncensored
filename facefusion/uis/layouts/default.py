import gradio

from facefusion import state_manager
from facefusion.uis.components import settings_guide
from facefusion.uis.components import about, age_modifier_options, background_remover_options, deep_swapper_options, download, execution, execution_thread_count, expression_restorer_options, face_debugger_options, face_detector, face_editor_options, face_enhancer_options, face_landmarker, face_masker, face_selector, face_swapper_options, face_tracker, frame_colorizer_options, frame_enhancer_options, instant_runner, job_manager, job_runner, lip_syncer_options, memory, output, output_options, preview, preview_options, processors, source, target, temp_frame, terminal, trim_frame, ui_workflow, voice_extractor, workflow


def pre_check() -> bool:
	return True


def render() -> gradio.Blocks:
	with gradio.Blocks() as layout:
		with gradio.Row(elem_id = 'facefusion-workspace'):
			with gradio.Column(scale = 4, min_width = 290):
				with gradio.Blocks():
					face_swapper_options.render()
				settings_guide.render_model_preset()
				with gradio.Blocks():
					processors.render()
				with gradio.Accordion('Additional processor settings', open = False):
					age_modifier_options.render()
					background_remover_options.render()
					deep_swapper_options.render()
					expression_restorer_options.render()
					face_debugger_options.render()
					face_editor_options.render()
					face_enhancer_options.render()
					frame_colorizer_options.render()
					frame_enhancer_options.render()
					lip_syncer_options.render()
					voice_extractor.render()
				with gradio.Accordion('Performance and export settings', open = False):
					workflow.render()
					execution.render()
					execution_thread_count.render()
					download.render()
					memory.render()
					temp_frame.render()
					output_options.render()
			with gradio.Column(scale = 4, min_width = 275):
				with gradio.Blocks():
					source.render()
				with gradio.Blocks():
					target.render()
				with gradio.Blocks():
					output.render()
				settings_guide.render_recovery()
				with gradio.Blocks():
					ui_workflow.render()
					instant_runner.render()
					job_runner.render()
					job_manager.render()
				with gradio.Accordion('Render log', open = False):
					terminal.render()
			with gradio.Column(scale = 7, min_width = 350):
				with gradio.Blocks():
					preview.render()
					preview_options.render()
				with gradio.Blocks():
					trim_frame.render()
				with gradio.Blocks():
					face_selector.render()
				with gradio.Accordion('Face detection and blending', open = False):
					face_tracker.render()
					face_masker.render()
					face_detector.render()
					face_landmarker.render()
				with gradio.Accordion('Help with this preview', open = False):
					settings_guide.render_guide()
				with gradio.Accordion('About FaceFusion', open = False):
					about.render()
	return layout


def listen() -> None:
	processors.listen()
	age_modifier_options.listen()
	background_remover_options.listen()
	deep_swapper_options.listen()
	expression_restorer_options.listen()
	face_debugger_options.listen()
	face_editor_options.listen()
	face_enhancer_options.listen()
	face_swapper_options.listen()
	frame_colorizer_options.listen()
	frame_enhancer_options.listen()
	lip_syncer_options.listen()
	execution.listen()
	execution_thread_count.listen()
	download.listen()
	memory.listen()
	temp_frame.listen()
	output_options.listen()
	source.listen()
	target.listen()
	output.listen()
	instant_runner.listen()
	job_runner.listen()
	job_manager.listen()
	terminal.listen()
	preview.listen()
	preview_options.listen()
	trim_frame.listen()
	face_selector.listen()
	face_tracker.listen()
	face_masker.listen()
	face_detector.listen()
	face_landmarker.listen()
	voice_extractor.listen()
	workflow.listen()
	settings_guide.listen((
		processors, face_swapper_options, face_enhancer_options, face_detector, face_landmarker,
		face_masker, face_selector, face_tracker, execution, execution_thread_count, memory,
		output_options, workflow, ui_workflow, temp_frame, age_modifier_options,
		background_remover_options, deep_swapper_options, expression_restorer_options,
		face_debugger_options, face_editor_options, frame_colorizer_options, frame_enhancer_options,
		lip_syncer_options, voice_extractor, download
	))


def run(ui : gradio.Blocks) -> None:
	ui.launch(favicon_path = 'facefusion.ico', inbrowser = state_manager.get_item('open_browser'))
