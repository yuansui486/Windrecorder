import hashlib
import subprocess
import time
from pathlib import Path

import streamlit as st
from PIL import Image

import windrecorder.record as record
import windrecorder.utils as utils
from windrecorder import __version__, file_utils
from windrecorder.config import config
from windrecorder.const import OCR_SUPPORT_CONFIG
from windrecorder.logger import get_logger
from windrecorder.utils import get_text as _t

logger = get_logger(__name__)

lang_map = utils.d_lang["lang_map"]


def set_config_lang(lang_name):
    inverted_lang_map = {v: k for k, v in lang_map.items()}
    lang_code = inverted_lang_map.get(lang_name)

    if not lang_code:
        logger.error(f"Invalid language name: {lang_name}")
        return

    config.set_and_save_config("lang", lang_code)


def render():
    st.markdown(_t("set_md_title"))

    col1b, col2b, col3b = st.columns([1, 0.5, 1.5])
    with col1b:
        # 更新数据库
        st.markdown(_t("set_md_index_db"))

        # 绘制数据库提示横幅
        draw_db_status()

        def update_database_clicked():
            st.session_state.update_button_disabled = True

        col1, col2 = st.columns([1, 1])
        with col1:
            # 设置ocr引擎
            ocr_engine = st.selectbox(
                _t("set_selectbox_local_ocr_engine"),
                config.support_ocr_lst,
                index=[index for index, value in enumerate(config.support_ocr_lst) if value == config.ocr_engine][0],
                help=_t("set_selectbox_local_ocr_engine_help"),
            )

        with col2:
            # 设定ocr引擎语言
            if "os_support_lang" not in st.session_state:  # 获取系统支持的OCR语言
                st.session_state.os_support_lang = utils.get_os_support_lang()

            ocr_lang_index = legal_ocr_lang_index()
            if ocr_engine == "Windows.Media.Ocr.Cli":
                config_ocr_lang = st.selectbox(
                    _t("set_selectbox_ocr_lang"),
                    st.session_state.os_support_lang,
                    index=ocr_lang_index,
                    help=_t("set_help_ocr_lang_windows_ocr_engine"),
                )
                third_party_engine_ocr_lang = config.third_party_engine_ocr_lang
            else:
                config_ocr_lang = config.ocr_lang
                if OCR_SUPPORT_CONFIG[ocr_engine]["support_multiple_languages"]:
                    third_party_engine_ocr_lang = st.multiselect(
                        label=_t("set_selectbox_ocr_lang"),
                        options=[value for value in OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"].values()],
                        default=[
                            value
                            for key, value in OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"].items()
                            if key in config.third_party_engine_ocr_lang
                        ],
                    )
                else:
                    try:
                        third_party_engine_ocr_lang_index = [
                            index
                            for index, value in enumerate(OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"])
                            if value == config.third_party_engine_ocr_lang[0]
                        ][0]
                    except (KeyError, IndexError):
                        third_party_engine_ocr_lang_index = 0
                    third_party_engine_ocr_lang = st.selectbox(
                        _t("set_selectbox_ocr_lang"),
                        [value for value in OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"].values()],
                        index=third_party_engine_ocr_lang_index,
                        disabled=True if len(OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"]) < 2 else False,
                        help=_t("set_help_ocr_lang_third_party_engine"),
                    )

                if ocr_engine == "TesseractOCR":
                    st.info(
                        "Before applying, please ensure the chose language pack has been installed. (https://github.com/tesseract-ocr/tessdata/)"
                    )

            if config.OCR_index_strategy == 0:
                update_db_btn = st.button(
                    _t("set_btn_update_db_manual"),
                    type="secondary",
                    key="update_button_key",
                    disabled=st.session_state.get("update_button_disabled", False),
                    on_click=update_database_clicked,
                )
                is_shutdown_pasocon_after_updatedDB = st.checkbox(
                    _t("set_checkbox_shutdown_after_updated"),
                    value=False,
                    disabled=st.session_state.get("update_button_disabled", False),
                )
            else:
                update_db_btn = False
                is_shutdown_pasocon_after_updatedDB = False
                st.empty()

        index_reduce_same_content_at_different_time = st.checkbox(
            label=_t("set_checkbox_reduce_same_content_at_different_time"),
            value=config.index_reduce_same_content_at_different_time,
        )

        recycle_deleted_files = st.checkbox(
            label=_t("set_checkbox_recycle_deleted_files"),
            help=_t("set_help_recycle_deleted_files"),
            value=config.recycle_deleted_files,
        )

        # 更新数据库按钮
        if update_db_btn:
            try:
                st.divider()
                estimate_time_str = utils.estimate_indexing_time()  # 预估剩余时间
                with st.spinner(_t("set_text_updating_db").format(estimate_time_str=estimate_time_str)):
                    timeCost = time.time()  # 预埋计算实际时长
                    from windrecorder import ocr_manager

                    ocr_manager.ocr_manager_main()  # 更新数据库

                    timeCost = time.time() - timeCost
            except Exception as ex:
                st.exception(ex)
            else:
                timeCostStr = utils.convert_seconds_to_hhmmss(timeCost)
                st.success(
                    _t("set_text_db_updated_successful").format(timeCostStr=timeCostStr),
                    icon="🧃",
                )
            finally:
                if is_shutdown_pasocon_after_updatedDB:
                    subprocess.run(["shutdown", "-s", "-t", "60"], shell=True)
                st.snow()
                st.session_state.update_button_disabled = False
                st.button(_t("set_btn_got_it"), key="setting_reset")

        st.divider()

        # OCR 时忽略屏幕四边的区域范围
        col1pb, col2pb = st.columns([1, 1])
        with col1pb:
            st.markdown(_t("set_md_ocr_ignore_area"), help=_t("set_md_ocr_ignore_area_help"))
        with col2pb:
            st.session_state.ocr_screenshot_refer_used = st.toggle(_t("set_toggle_use_screenshot_as_refer"), False)

        # 当检测到多显示器时提供设置选项
        if (
            st.session_state.display_count > 1 and config.multi_display_record_strategy == "all"
        ):  # 当使用多显示器录制时。此处所用变量会在 recording.py 先进行初始化
            crop_display_selector = st.selectbox(_t("set_text_choose_displays"), st.session_state.display_info_formatted)
            crop_display_index = st.session_state.display_info_formatted.index(crop_display_selector)
        else:
            crop_display_index = 0

        if "ocr_padding_URBL" not in st.session_state:
            st.session_state.ocr_padding_URBL = utils.ensure_list_divisible_by_num(config.ocr_image_crop_URBL, 4)
            if len(st.session_state.ocr_padding_URBL) < st.session_state.display_count * 4:  # 不足时补齐参数 slot
                for i in range(st.session_state.display_count - (len(st.session_state.ocr_padding_URBL) // 4)):
                    st.session_state.ocr_padding_URBL.extend([6, 6, 6, 3])

        col1pa, col2pa, col3pa = st.columns([0.5, 0.5, 1])
        with col1pa:
            st.session_state.ocr_padding_URBL[0 + crop_display_index * 4] = st.number_input(
                _t("set_text_top_padding"),
                value=st.session_state.ocr_padding_URBL[0 + crop_display_index * 4],
                min_value=0,
                max_value=40,
            )
            st.session_state.ocr_padding_URBL[2 + crop_display_index * 4] = st.number_input(
                _t("set_text_bottom_padding"),
                value=st.session_state.ocr_padding_URBL[2 + crop_display_index * 4],
                min_value=0,
                max_value=40,
            )

        with col2pa:
            st.session_state.ocr_padding_URBL[3 + crop_display_index * 4] = st.number_input(
                _t("set_text_left_padding"),
                value=st.session_state.ocr_padding_URBL[3 + crop_display_index * 4],
                min_value=0,
                max_value=40,
            )
            st.session_state.ocr_padding_URBL[1 + crop_display_index * 4] = st.number_input(
                _t("set_text_right_padding"),
                value=st.session_state.ocr_padding_URBL[1 + crop_display_index * 4],
                min_value=0,
                max_value=40,
            )
        with col3pa:
            image_setting_crop_refer = screen_ignore_padding(
                st.session_state.ocr_padding_URBL[0 + crop_display_index * 4],
                st.session_state.ocr_padding_URBL[1 + crop_display_index * 4],
                st.session_state.ocr_padding_URBL[2 + crop_display_index * 4],
                st.session_state.ocr_padding_URBL[3 + crop_display_index * 4],
                use_screenshot=st.session_state.ocr_screenshot_refer_used,
                screenshot_display_index=crop_display_index + 1,
            )
            st.image(image_setting_crop_refer)

        st.divider()

        # 界面设置组
        col1_ui, col2_ui = st.columns([1, 1])
        with col1_ui:
            st.markdown(_t("set_md_gui"))
            # 一日之时启用三栏布局
            config_enable_3_columns_in_oneday = st.checkbox(
                _t("set_checkbox_enable_3_columns_in_oneday"),
                value=config.enable_3_columns_in_oneday,
                help=_t("set_help_enable_3_columns_in_oneday"),
            )
            # 使用中文形近字进行搜索
            if str(config.ocr_lang).startswith("zh"):
                config_use_similar_ch_char_to_search = st.checkbox(
                    _t("set_checkbox_use_similar_zh_char_to_search"),
                    value=config.use_similar_ch_char_to_search,
                    help=_t("set_checkbox_use_similar_zh_char_to_search_help"),
                )
            else:
                config_use_similar_ch_char_to_search = config.use_similar_ch_char_to_search
            # 搜索中推荐近似词
            if config.img_embed_module_install:
                config_enable_synonyms_recommend = st.checkbox(
                    _t("set_checkbox_synonyms_recommand"),
                    value=config.enable_synonyms_recommend,
                    help=_t("set_help_synonyms_recommand"),
                )
            else:
                config_enable_synonyms_recommend = False

            enable_month_lightbox_watermark = st.checkbox(
                _t("lb_checkbox_add_watermark"), value=config.enable_month_lightbox_watermark
            )

        with col2_ui:
            config_wordcloud_user_stop_words = st.text_area(
                _t("set_input_wordcloud_filter"),
                help=_t("set_input_wordcloud_filter_help"),
                value=utils.list_to_string(config.wordcloud_user_stop_words),
            )

        # 每页结果最大数量
        col1_ui2, col2_ui2 = st.columns([1, 1])
        with col1_ui2:
            day_begin_time_list = [
                ("00:00", 0),
                ("01:00", 60),
                ("02:00", 120),
                ("03:00", 180),
                ("04:00", 240),
                ("05:00", 300),
                ("06:00", 360),
            ]

            option_day_begin_time_oneday = st.selectbox(
                _t("set_input_day_begin_minutes"),
                index=find_index_in_tuple_timelist(list=day_begin_time_list, target=config.day_begin_minutes),
                options=[item[0] for item in day_begin_time_list],
                help=_t("set_help_day_begin_minutes"),
            )

            config_max_search_result_num = st.number_input(
                _t("set_input_max_num_search_page"),
                min_value=5,
                max_value=500,
                value=config.max_page_result,
            )

        with col2_ui2:
            # 「一天之时」时间轴的横向缩略图数量
            config_oneday_timeline_num = st.number_input(
                _t("set_input_oneday_timeline_thumbnail_num"),
                min_value=50,
                max_value=100,
                value=config.oneday_timeline_pic_num,
                help=_t("set_input_oneday_timeline_thumbnail_num_help"),
            )

            # imgemb 选项
            if config.img_embed_module_install and st.session_state.option_enable_img_embed_search:
                config_img_embed_search_recall_result_per_db = st.number_input(
                    _t("set_input_img_emb_max_recall_count"),
                    min_value=5,
                    max_value=100,
                    value=config.img_embed_search_recall_result_per_db,
                    help=_t("set_text_help_img_emb_max_recall_count"),
                )
            else:
                config_img_embed_search_recall_result_per_db = 30

        config_webui_access_password = st.text_input(
            f'🔒 {_t("set_pwd_text")}', value=config.webui_access_password_md5, help=_t("set_pwd_help"), type="password"
        )

        st.divider()

        # 音频录制设置组
        st.markdown("### 🎤 Audio Recording / 音频录制设置")

        # 启用音频录制
        config_enable_audio_recording = st.checkbox(
            "Enable Audio Recording / 启用音频录制",
            value=config.enable_audio_recording,
            help="Record system audio and microphone along with screen recording / 在录制屏幕的同时录制系统音频和麦克风",
        )

        if config_enable_audio_recording:
            col1_audio, col2_audio = st.columns([1, 1])

            with col1_audio:
                # 录制系统音频
                config_record_system_audio = st.checkbox(
                    "Record System Audio / 录制系统音频",
                    value=config.record_system_audio,
                    help="Record audio from applications (e.g. browser, media player) / 录制来自应用程序的音频（如浏览器、媒体播放器）",
                )

                # 录制麦克风
                config_record_mic_audio = st.checkbox(
                    "Record Microphone / 录制麦克风",
                    value=config.record_mic_audio,
                    help="Record audio from microphone / 录制来自麦克风的音频",
                )

                # ASR 开关
                config_enable_audio_asr = st.checkbox(
                    "Enable ASR (Speech-to-Text) / 启用语音转文字",
                    value=config.enable_audio_asr,
                    help="Automatically transcribe audio to text during idle maintenance / 在闲时自动将音频转为文字",
                )

                # 音频保留天数
                config_audio_store_day = st.number_input(
                    "Audio Retention Days / 音频保留天数",
                    min_value=1,
                    max_value=365,
                    value=config.audio_store_day,
                    help="Automatically delete audio files after this many days (ASR text will be kept) / 超过此天数的音频文件将被自动删除（但 ASR 文本会保留）",
                )

            with col2_audio:
                # 检测音频设备按钮
                if st.button("🔍 Detect Audio Devices / 检测音频设备", help="Scan for available audio devices / 扫描可用的音频设备"):
                    with st.spinner("Detecting audio devices... / 正在检测音频设备..."):
                        devices = utils.get_audio_devices()
                        st.session_state.audio_devices = devices

                # 显示检测到的设备
                if "audio_devices" in st.session_state:
                    devices = st.session_state.audio_devices

                    st.markdown("**Detected Devices / 检测到的设备:**")

                    if devices['all_devices']:
                        st.success(f"✅ Found {len(devices['all_devices'])} audio device(s) / 找到 {len(devices['all_devices'])} 个音频设备")
                        for i, device in enumerate(devices['all_devices'], 1):
                            st.text(f"  {i}. {device}")
                    else:
                        st.warning("⚠️ No audio devices found / 未找到音频设备")

            # 设备选择
            st.markdown("**Device Selection / 设备选择:**")
            col1_dev, col2_dev = st.columns([1, 1])

            with col1_dev:
                # 系统音频设备
                devices = st.session_state.get("audio_devices", {}).get('all_devices', [config.system_audio_device_name])
                try:
                    idx = devices.index(config.system_audio_device_name)
                except ValueError:
                    idx = 0

                config_system_audio_device_name = st.selectbox(
                    "System Audio / 系统音频",
                    options=devices,
                    index=idx,
                    help="Select device for system sounds (Stereo Mix, Virtual Audio Cable) / 选择系统音频设备（立体声混音、虚拟音频线）",
                )

                if st.button("🎵 Test / 测试", key="test_sys"):
                    success, msg, _ = utils.test_audio_device(config_system_audio_device_name, 2)
                    (st.success if success else st.error)(f"{'✅' if success else '❌'} {msg}")

            with col2_dev:
                # 麦克风设备
                devices = st.session_state.get("audio_devices", {}).get('all_devices', [config.mic_audio_device_name])
                try:
                    idx = devices.index(config.mic_audio_device_name)
                except ValueError:
                    idx = 0

                config_mic_audio_device_name = st.selectbox(
                    "Microphone / 麦克风",
                    options=devices,
                    index=idx,
                    help="Select microphone device (headset, USB mic) / 选择麦克风设备（耳机、USB麦克风）",
                )

                if st.button("🎤 Test / 测试", key="test_mic"):
                    success, msg, _ = utils.test_audio_device(config_mic_audio_device_name, 2)
                    (st.success if success else st.error)(f"{'✅' if success else '❌'} {msg}")

            # ASR 设置
            if config_enable_audio_asr:
                with st.expander("⚙️ Advanced ASR Settings / ASR 高级设置"):
                    col1_asr, col2_asr = st.columns([1, 1])

                    with col1_asr:
                        config_asr_use_gpu = st.checkbox(
                            "Use GPU for ASR / 使用 GPU 加速",
                            value=config.asr_use_gpu,
                            help="Enable GPU acceleration if you have NVIDIA GPU with CUDA / 如果有 NVIDIA GPU 和 CUDA，可启用 GPU 加速",
                        )

                        config_batch_size_asr_in_idle = st.number_input(
                            "Batch Size / 批处理大小",
                            min_value=1,
                            max_value=20,
                            value=config.batch_size_asr_in_idle,
                            help="Number of audio files to process in each idle maintenance cycle / 每次闲时维护处理的音频文件数量",
                        )

                    with col2_asr:
                        config_asr_min_text_length = st.number_input(
                            "Min Text Length / 最小文本长度",
                            min_value=1,
                            max_value=50,
                            value=config.asr_min_text_length,
                            help="Texts shorter than this will be filtered as noise / 短于此长度的文本将被过滤为噪音",
                        )

                        config_asr_repetitive_threshold = st.slider(
                            "Repetitive Threshold / 重复阈值",
                            min_value=0.1,
                            max_value=1.0,
                            value=config.asr_repetitive_threshold,
                            step=0.05,
                            help="Lower values filter more repetitive text (e.g. song lyrics) / 较低的值会过滤更多重复文本（如歌词）",
                        )

                    # 音乐过滤关键词
                    config_asr_music_filter_keywords = st.text_input(
                        "Music Filter Keywords / 音乐过滤关键词",
                        value=",".join(config.asr_music_filter_keywords) if config.asr_music_filter_keywords else "",
                        help="Comma-separated keywords to filter out music (e.g. 'lalala,nanana') / 用逗号分隔的关键词，用于过滤音乐（如 'lalala,nanana'）",
                    )
        else:
            # 禁用时使用现有配置
            config_record_system_audio = config.record_system_audio
            config_record_mic_audio = config.record_mic_audio
            config_enable_audio_asr = config.enable_audio_asr
            config_audio_store_day = config.audio_store_day
            config_system_audio_device_name = config.system_audio_device_name
            config_mic_audio_device_name = config.mic_audio_device_name
            config_asr_use_gpu = config.asr_use_gpu
            config_batch_size_asr_in_idle = config.batch_size_asr_in_idle
            config_asr_min_text_length = config.asr_min_text_length
            config_asr_repetitive_threshold = config.asr_repetitive_threshold
            config_asr_music_filter_keywords = ""

        # 选择语言
        lang_selection = list(lang_map.values())
        lang_index = lang_selection.index(lang_map[config.lang])

        language_option = st.selectbox(
            "🌎 Interface Language / 更改显示语言 / 表示言語を変更する",
            lang_selection,
            index=lang_index,
        )

        st.divider()

        if st.button(
            "Save and Apply All Changes / " + _t("text_apply_changes")
            if config.lang != "en"
            else "Save and Apply All Changes",
            type="primary",
            key="SaveBtnGeneral",
        ):
            set_config_lang(language_option)
            config.set_and_save_config("enable_3_columns_in_oneday", config_enable_3_columns_in_oneday)
            config.set_and_save_config("max_page_result", config_max_search_result_num)
            config.set_and_save_config("ocr_engine", ocr_engine)
            config.set_and_save_config("ocr_lang", config_ocr_lang)
            config.set_and_save_config(
                "third_party_engine_ocr_lang",
                [
                    k
                    for k, v in OCR_SUPPORT_CONFIG[ocr_engine]["support_lang_option"].items()
                    if v in third_party_engine_ocr_lang
                ],
            )
            config.set_and_save_config(
                "index_reduce_same_content_at_different_time", index_reduce_same_content_at_different_time
            )
            config.set_and_save_config("use_similar_ch_char_to_search", config_use_similar_ch_char_to_search)
            config.set_and_save_config("enable_synonyms_recommend", config_enable_synonyms_recommend)
            config.set_and_save_config("img_embed_search_recall_result_per_db", config_img_embed_search_recall_result_per_db)
            config.set_and_save_config("enable_month_lightbox_watermark", enable_month_lightbox_watermark)
            config.set_and_save_config("recycle_deleted_files", recycle_deleted_files)

            # 更改了一天之时缩略图相关选项时，清空缓存时间轴缩略图
            day_begin_minutes = find_value_in_tuple_timelist_by_str(
                list=day_begin_time_list, target=option_day_begin_time_oneday
            )
            if day_begin_minutes != config.day_begin_minutes or config_oneday_timeline_num != config.oneday_timeline_pic_num:
                file_utils.empty_directory(config.timeline_result_dir_ud)
            config.set_and_save_config("day_begin_minutes", day_begin_minutes)
            config.set_and_save_config("oneday_timeline_pic_num", config_oneday_timeline_num)

            config.set_and_save_config(
                "ocr_image_crop_URBL",
                st.session_state.ocr_padding_URBL,
            )
            config.set_and_save_config(
                "wordcloud_user_stop_words",
                utils.string_to_list(config_wordcloud_user_stop_words),
            )

            # 保存音频相关配置
            config.set_and_save_config("enable_audio_recording", config_enable_audio_recording)
            config.set_and_save_config("record_system_audio", config_record_system_audio)
            config.set_and_save_config("record_mic_audio", config_record_mic_audio)
            config.set_and_save_config("enable_audio_asr", config_enable_audio_asr)
            config.set_and_save_config("audio_store_day", config_audio_store_day)
            config.set_and_save_config("system_audio_device_name", config_system_audio_device_name)
            config.set_and_save_config("mic_audio_device_name", config_mic_audio_device_name)
            config.set_and_save_config("asr_use_gpu", config_asr_use_gpu)
            config.set_and_save_config("batch_size_asr_in_idle", config_batch_size_asr_in_idle)
            config.set_and_save_config("asr_min_text_length", config_asr_min_text_length)
            config.set_and_save_config("asr_repetitive_threshold", config_asr_repetitive_threshold)
            # 处理音乐过滤关键词
            music_keywords = [k.strip() for k in config_asr_music_filter_keywords.split(",") if k.strip()]
            config.set_and_save_config("asr_music_filter_keywords", music_keywords)

            # 如果有新密码输入，更改；如果留空，关闭功能
            if config_webui_access_password and config_webui_access_password != config.webui_access_password_md5:
                config.set_and_save_config(
                    "webui_access_password_md5", hashlib.md5(config_webui_access_password.encode("utf-8")).hexdigest()
                )
            elif len(config_webui_access_password) == 0:
                config.set_and_save_config("webui_access_password_md5", "")
            st.toast(_t("utils_toast_setting_saved"), icon="🦝")
            time.sleep(1)
            st.rerun()

    with col2b:
        st.empty()

    with col3b:
        # 关于
        # 从GitHub检查更新、添加提醒 - 位于设置页靠后的流程，以不打扰用户
        if "update_check" not in st.session_state:
            try:
                with st.spinner(_t("set_update_checking")):
                    new_version = utils.get_new_version_if_available()
                if new_version is not None:
                    st.session_state.update_info = _t("set_update_new").format(tool_version=new_version) + _t(
                        "set_update_changelog"
                    )
                    st.session_state.update_need = True
                    st.session_state.update_badge_emoji = "✨"
                else:
                    st.session_state.update_info = _t("set_update_latest")
            except Exception as e:
                st.session_state.update_info = _t("set_update_fail").format(e=e)
            st.session_state["update_check"] = True

        if "about_image_b64" not in st.session_state:
            st.session_state.about_image_b64 = utils.image_to_base64("__assets__\\readme_racoonNagase.png")
        st.markdown(
            f"<img align='right' style='max-width: 100%;max-height: 100%;' src='data:image/png;base64, {st.session_state.about_image_b64}'/>",
            unsafe_allow_html=True,
        )

        about_markdown = (
            Path(f"{config.config_src_dir}\\about_{config.lang}.md")
            .read_text(encoding="utf-8")
            .format(
                version=__version__,
                update_info=st.session_state.update_info,
            )
        )
        st.markdown(about_markdown, unsafe_allow_html=True)


# 数据库的前置更新索引状态提示
def draw_db_status():
    count, nocred_count = file_utils.get_videos_and_ocred_videos_count(config.record_videos_dir_ud)
    timeCostStr = utils.estimate_indexing_time()
    if config.OCR_index_strategy == 1:
        # 启用自动索引
        if nocred_count == 1 and record.is_recording():
            st.success(
                _t("set_text_one_video_to_index").format(nocred_count=nocred_count, count=count),
                icon="✅",
            )
        elif nocred_count == 0:
            st.success(
                _t("set_text_no_video_need_index").format(nocred_count=nocred_count, count=count),
                icon="✅",
            )
        else:
            st.success(
                _t("set_text_some_video_will_be_index").format(nocred_count=nocred_count, count=count),
                icon="✅",
            )
    elif config.OCR_index_strategy == 0:
        if nocred_count == 1 and record.is_recording():
            st.success(
                _t("set_text_one_video_to_index").format(nocred_count=nocred_count, count=count),
                icon="✅",
            )
        elif nocred_count >= 1:
            st.warning(
                _t("set_text_video_not_index").format(nocred_count=nocred_count, count=count, timeCostStr=timeCostStr),
                icon="🧭",
            )
        else:
            st.success(
                _t("set_text_no_video_need_index").format(nocred_count=nocred_count, count=count),
                icon="✅",
            )


# 检查配置使用的ocr语言，如果不在则设为可用的第一个
def legal_ocr_lang_index():
    os_support_lang_list = st.session_state.os_support_lang  # 获取系统支持的语言

    if config.ocr_lang in os_support_lang_list:  # 如果配置项在支持的列表中，返回索引值
        return os_support_lang_list.index(config.ocr_lang)
    else:  # 如果配置项不在支持的列表中，返回默认值，config设定为支持的第一项
        config.set_and_save_config("ocr_lang", os_support_lang_list[0])
        return 0


# 调整屏幕忽略范围的设置可视化
def screen_ignore_padding(topP, rightP, bottomP, leftP, use_screenshot=False, screenshot_display_index=1):
    image_padding_refer = Image.open("__assets__\\setting-crop-refer-pure.png")
    indicator_overdraw_color = (100, 0, 255, 80)

    if use_screenshot:
        image_padding_refer = utils.get_screenshot_of_display(screenshot_display_index)
        image_padding_refer_width, image_padding_refer_height = image_padding_refer.size
    else:
        image_padding_refer_width = st.session_state.display_info[screenshot_display_index]["width"]
        image_padding_refer_height = st.session_state.display_info[screenshot_display_index]["height"]

    if image_padding_refer_width > image_padding_refer_height:
        image_padding_refer_height = int(350 * image_padding_refer_height / image_padding_refer_width)
        image_padding_refer = image_padding_refer.resize((350, image_padding_refer_height))
        if use_screenshot:
            image_padding_refer_fade = Image.new("RGBA", (350, image_padding_refer_height), (255, 233, 216, 100))  # 添加背景色蒙层
            image_padding_refer.paste(image_padding_refer_fade, (0, 0), image_padding_refer_fade)
    else:
        image_padding_refer_width = int(350 * image_padding_refer_width / image_padding_refer_height)
        image_padding_refer = image_padding_refer.resize((image_padding_refer_width, 350))
        if use_screenshot:
            image_padding_refer_fade = Image.new("RGBA", (image_padding_refer_width, 350), (255, 233, 216, 100))  # 添加背景色蒙层
            image_padding_refer.paste(image_padding_refer_fade, (0, 0), image_padding_refer_fade)

    image_padding_refer_width, image_padding_refer_height = image_padding_refer.size
    topP_height = round(image_padding_refer_height * topP * 0.01)
    bottomP_height = round(image_padding_refer_height * bottomP * 0.01)
    leftP_width = round(image_padding_refer_width * leftP * 0.01)
    rightP_width = round(image_padding_refer_width * rightP * 0.01)

    image_color_area = Image.new("RGBA", (image_padding_refer_width, topP_height), indicator_overdraw_color)
    image_padding_refer.paste(image_color_area, (0, 0), image_color_area)
    image_color_area = Image.new("RGBA", (image_padding_refer_width, bottomP_height), indicator_overdraw_color)
    image_padding_refer.paste(
        image_color_area,
        (0, image_padding_refer_height - bottomP_height),
        image_color_area,
    )
    image_color_area = Image.new("RGBA", (leftP_width, image_padding_refer_height), indicator_overdraw_color)
    image_padding_refer.paste(image_color_area, (0, 0), image_color_area)
    image_color_area = Image.new("RGBA", (rightP_width, image_padding_refer_height), indicator_overdraw_color)
    image_padding_refer.paste(
        image_color_area,
        (image_padding_refer_width - rightP_width, 0),
        image_color_area,
    )

    return image_padding_refer


# 寻找配置项分钟数在 timelist 对应时间表达的 index
def find_index_in_tuple_timelist(list, target):
    for i in range(len(list)):
        if list[i][1] == target:
            return i
    return 0


# 根据输入 str，寻找 timelist 对应的分钟数
def find_value_in_tuple_timelist_by_str(list, target):
    for i in range(len(list)):
        if list[i][0] == target:
            return list[i][1]
    return 1
