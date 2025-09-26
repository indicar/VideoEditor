import sys, cv2, ffmpeg, time, os, json, pygame
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QMenuBar, QProgressBar, QStyle)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QPoint, QRect, QTimer, QMutex
from PyQt6.QtGui import QImage, QPixmap, QPainter, QResizeEvent, QMouseEvent, QCursor, QColor, QPen, QBrush, QPolygon, QAction, QActionGroup

# --- CONFIG & TRANSLATIONS ---
CONFIG_FILE = 'config.json'
TRANSLATIONS = {
    'en': {
        'window_title': "Video Editor", 'load_video_prompt': "Load a video to start",
        'play_label': "Play", 'selection_label': "Sel", 'length_label': "Len",
        'load_button': "Load Video", 'trim_button': "Trim and Save", 'status_ready': "Ready",
        'status_loading': "Loading...", 'status_loaded_audio': "Video and audio loaded.",
        'status_loaded_no_audio': "Video loaded (no audio track).", 'status_load_error': "Error loading video: {e}",
        'status_trimming': "Trimming...", 'status_trim_saved': "Video saved to {path}",
        'status_trim_cancelled': "Trim cancelled.", 'status_invalid_range': "Error: Invalid range.",
        'dialog_load_video': "Select Video File", 'dialog_save_video': "Save Video As",
        'dialog_video_files': "Video Files", 'menu_settings': "&Settings", 'menu_language': "&Language",
    },
    'ru': {
        'window_title': "Видеоредактор", 'load_video_prompt': "Загрузите видео для начала работы",
        'play_label': "Play", 'selection_label': "Выб", 'length_label': "Длина",
        'load_button': "Загрузить видео", 'trim_button': "Обрезать и сохранить", 'status_ready': "Готов к работе",
        'status_loading': "Загрузка...", 'status_loaded_audio': "Видео и аудио загружены.",
        'status_loaded_no_audio': "Видео загружено (аудиодорожка отсутствует).", 'status_load_error': "Ошибка загрузки видео: {e}",
        'status_trimming': "Выполняется обрезка...", 'status_trim_saved': "Видео сохранено в {path}",
        'status_trim_cancelled': "Обрезка отменена.", 'status_invalid_range': "Ошибка: Неверный диапазон.",
        'dialog_load_video': "Выбрать видеофайл", 'dialog_save_video': "Сохранить видео как",
        'dialog_video_files': "Видеофайлы", 'menu_settings': "&Настройки", 'menu_language': "&Язык",
    }
}
DARK_STYLESHEET = """QWidget{background-color:#2d2d2d;color:#f0f0f0;font-family:Segoe UI;font-size:10pt}QMenuBar{background-color:#3d3d3d}QMenuBar::item:selected{background-color:#5a5a5a}QMenu{background-color:#3d3d3d;border:1px solid #555}QMenu::item:selected{background-color:#0078d7}QLabel{border:none}QPushButton{background-color:#4a4a4a;border:1px solid #555;padding:5px 10px;border-radius:4px}QPushButton:hover{background-color:#5a5a5a}QPushButton:pressed{background-color:#3a3a3a}QPushButton:disabled{background-color:#404040;color:#888;border-color:#444}QProgressBar{border:1px solid #555;border-radius:4px;text-align:center;background-color:#3d3d3d;color:#f0f0f0}QProgressBar::chunk{background-color:#0078d7;border-radius:3px}"""

def load_config():
    if not os.path.exists(CONFIG_FILE): return {'language': 'en'}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return {'language': 'en'}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, indent=4)

# --- WIDGETS & THREADS ---
class RangeSlider(QWidget):
    start_changed,end_changed,playhead_moved = [pyqtSignal(int) for _ in range(3)]; start_drag_finished = pyqtSignal()
    def __init__(self,p=None):super().__init__(p);self.setMinimumHeight(35);self.setCursor(Qt.CursorShape.PointingHandCursor);self._min,self._max,self._start,self._end,self._playhead=0,0,0,0,0;self.dragged_handle=None
    def set_range(self,m,M):self._min,self._max=m,M;self.set_start(m);self.set_end(M);self.set_playhead(m);self.update()
    def set_start(self,v):self._start=max(self._min,min(v,self._end));self.update()
    def set_end(self,v):self._end=min(self._max,max(v,self._start));self.update()
    def set_playhead(self,v):self._playhead=max(self._min,min(v,self._max));self.update()
    def get_start(self):return self._start
    def get_end(self):return self._end
    def get_playhead(self):return self._playhead
    def _v2p(self,v):return int(((v-self._min)/(self._max-self._min))*self.width()) if self._max!=self._min else 0
    def _p2v(self,p):return int((p/self.width())*(self._max-self._min)+self._min) if self.width()!=0 else 0
    def _draw_h(self,p,pos,c):p.setBrush(c);p.setPen(Qt.PenStyle.NoPen);t,b=QPolygon([QPoint(pos-6,0),QPoint(pos+6,0),QPoint(pos,8)]),QPolygon([QPoint(pos-6,self.height()),QPoint(pos+6,self.height()),QPoint(pos,self.height()-8)]);p.drawPolygon(t);p.drawPolygon(b)
    def paintEvent(self,e):p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);t=self.rect().adjusted(0,12,0,-12);p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor("#3d3d3d"));p.drawRect(t);s,e=self._v2p(self._start),self._v2p(self._end);sr=QRect(s,t.y(),e-s,t.height());p.setBrush(QColor(0,120,215,128));p.drawRect(sr);self._draw_h(p,s,QColor("#0090f0"));self._draw_h(p,e,QColor("#0090f0"));pp=self._v2p(self._playhead);p.setPen(QPen(QColor("#E81123"),3));p.drawLine(pp,0,pp,self.height())
    def mousePressEvent(self,e:QMouseEvent):
        p=e.pos().x();s,E=self._v2p(self._start),self._v2p(self._end)
        if abs(p-s)<10: self.dragged_handle = 'start'
        elif abs(p-E)<10: self.dragged_handle = 'end'
        else: self.dragged_handle = 'playhead'; self.set_playhead(self._p2v(p)); self.playhead_moved.emit(self._playhead)
    def mouseMoveEvent(self,e:QMouseEvent):v=self._p2v(e.pos().x());h=self.dragged_handle; (self.set_start(v),self.start_changed.emit(self._start)) if h=='start' else (self.set_end(v),self.end_changed.emit(self._end)) if h=='end' else (self.set_playhead(v),self.playhead_moved.emit(self._playhead)) if h=='playhead' else None
    def mouseReleaseEvent(self,e:QMouseEvent): self.start_drag_finished.emit() if self.dragged_handle=='start' else None; self.dragged_handle=None

class PlaybackThread(QThread):
    new_frame=pyqtSignal(int,object);playback_finished=pyqtSignal()
    def __init__(self,c,f,sf,ef,p=None):super().__init__(p);self.cap,self.fps,self.current_frame_idx,self.end_frame=c,f,sf,ef;self.is_running=True
    def run(self):
        if not self.fps or self.fps==0:self.is_running=False;self.playback_finished.emit();return
        d=1/self.fps
        while self.is_running and self.current_frame_idx<=self.end_frame:
            s=time.time();self.cap.set(cv2.CAP_PROP_POS_FRAMES,self.current_frame_idx);r,fr=self.cap.read()
            if not r:break
            self.new_frame.emit(self.current_frame_idx,fr);self.current_frame_idx+=1;e=time.time()-s;t=d-e;time.sleep(t) if t>0 else None
        self.playback_finished.emit()
    def stop(self):self.is_running=False

class TrimThread(QThread):
    finished = pyqtSignal(str, str)
    def __init__(self,i,s,e,o,tr):
        super().__init__()
        self.i, self.start_time, self.end_time, self.o, self.tr = i,s,e,o,tr
    def run(self):
        try:
            input_stream = ffmpeg.input(self.i)
            trimmed_stream = ffmpeg.output(input_stream, self.o, ss=self.start_time, to=self.end_time, vcodec='libx264', acodec='copy')
            ffmpeg.run(trimmed_stream, overwrite_output=True, quiet=True)
            self.finished.emit('status_trim_saved', self.o)
        except ffmpeg.Error as e:
            error_details = e.stderr.decode('utf8', errors='ignore')
            self.finished.emit('status_trim_error', error_details)
        except Exception as e:
            self.finished.emit('status_trim_error', str(e))

class VideoEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.config=load_config();self.current_lang=self.config.get('language','en')
        self.cap,self.playback_thread,self.input_file=None,None,None;self.duration,self.fps,self.total_frames=0,0,0;self.temp_audio_file,self.has_audio="temp_audio.wav",False;self.start_time_offset=0.0
        pygame.init();pygame.mixer.init()
        self.initUI()

    def tr(self,key,**kwargs):return TRANSLATIONS[self.current_lang].get(key,key).format(**kwargs)

    def initUI(self):
        self.main_layout=QVBoxLayout(self);self._setup_menu()
        self.video_label=QLabel();self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.video_label.setStyleSheet("background-color:black;color:#888;font-size:12pt");self.main_layout.addWidget(self.video_label,1)
        self.timeline=RangeSlider();self.timeline.playhead_moved.connect(self.set_position_from_timeline);self.timeline.start_changed.connect(self.update_time_label);self.timeline.end_changed.connect(self.update_time_label);self.timeline.start_drag_finished.connect(self.play_from_start_marker);self.main_layout.addWidget(self.timeline)
        cl=QHBoxLayout();self.play_button=QPushButton();self.play_button.clicked.connect(self.play_video);cl.addWidget(self.play_button);self.pause_button=QPushButton();self.pause_button.clicked.connect(self.pause_video);self.pause_button.setEnabled(False);cl.addWidget(self.pause_button);self.time_label=QLabel();self.time_label.setStyleSheet("color:#aaa;margin-left:10px");cl.addWidget(self.time_label);cl.addStretch();self.main_layout.addLayout(cl)
        bl=QHBoxLayout();self.load_button=QPushButton();self.load_button.clicked.connect(self.load_video);bl.addWidget(self.load_button);bl.addStretch();self.trim_button=QPushButton();self.trim_button.clicked.connect(self.trim_video);self.trim_button.setEnabled(False);self.trim_button.setStyleSheet("background-color:#0078d7;border-color:#005a9e");bl.addWidget(self.trim_button);self.main_layout.addLayout(bl)
        self.status_label=QLabel();self.status_label.setStyleSheet("color:#888;padding:2px");self.main_layout.addWidget(self.status_label);self.progress_bar=QProgressBar();self.progress_bar.setVisible(False);self.main_layout.addWidget(self.progress_bar)
        self.retranslate_ui()

    def _setup_menu(self):
        self.menu_bar=QMenuBar();self.main_layout.setMenuBar(self.menu_bar);settings_menu=self.menu_bar.addMenu("");lang_menu=settings_menu.addMenu("");lang_group=QActionGroup(self);lang_group.setExclusive(True)
        en_action=lang_group.addAction(QAction("English",self,checkable=True));ru_action=lang_group.addAction(QAction("Русский",self,checkable=True));en_action.triggered.connect(lambda:self.switch_language('en'));ru_action.triggered.connect(lambda:self.switch_language('ru'));lang_menu.addAction(en_action);lang_menu.addAction(ru_action)
        (en_action if self.current_lang=='en' else ru_action).setChecked(True)

    def retranslate_ui(self):
        self.setWindowTitle(self.tr('window_title'));self.video_label.setText(self.tr('load_video_prompt'));self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay));self.pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause));self.load_button.setText(self.tr('load_button'));self.trim_button.setText(self.tr('trim_button'));self.status_label.setText(self.tr('status_ready'));self.update_time_label()
        self.menu_bar.actions()[0].setText(self.tr('menu_settings'));self.menu_bar.actions()[0].menu().actions()[0].setText(self.tr('menu_language'))

    def switch_language(self,lang):self.current_lang=lang;self.config['language']=lang;save_config(self.config);self.retranslate_ui()

    def load_video(self,fp=None):
        self.pause_video()
        # Выгружаем и удаляем старый временный файл, если он был
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            pygame.mixer.music.unload()
            try:
                os.remove(self.temp_audio_file)
            except OSError:
                pass # Может быть занят, но мы все равно создадим новый

        if not fp:fp,_=QFileDialog.getOpenFileName(self,self.tr('dialog_load_video'),"",f"{self.tr('dialog_video_files')} (*.mp4 *.avi *.mkv)")
        if not fp: self.status_label.setText(self.tr('status_ready')); return
        
        try:
            self.status_label.setText(self.tr('status_loading'));QApplication.processEvents();self.input_file=fp
            if self.cap:self.cap.release()
            self.cap=cv2.VideoCapture(self.input_file);self.fps=self.cap.get(cv2.CAP_PROP_FPS);self.total_frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT));self.duration=self.total_frames/self.fps if self.fps>0 else 0
            
            # Генерируем уникальное имя файла, чтобы обмануть кэш pygame
            self.temp_audio_file = f"temp_audio_{int(time.time())}.wav"

            try:
                ffmpeg.input(self.input_file).output(self.temp_audio_file,format='wav',acodec='pcm_s16le').overwrite_output().run(quiet=True)
                pygame.mixer.music.load(self.temp_audio_file)
                self.has_audio=True
                self.status_label.setText(self.tr('status_loaded_audio'))
            except ffmpeg.Error:
                self.has_audio=False
                self.status_label.setText(self.tr('status_loaded_no_audio'))
            
            self.timeline.set_range(0,self.total_frames-1);self.trim_button.setEnabled(True);self.display_frame(0)
        except Exception as e:self.status_label.setText(self.tr('status_load_error',e=e))

    def play_video(self):
        if not self.cap or(self.playback_thread and self.playback_thread.isRunning()):return
        sf=self.timeline.get_playhead();ef=self.timeline.get_end();self.start_time_offset=sf/self.fps if self.fps>0 else 0
        if self.has_audio:pygame.mixer.music.play(start=self.start_time_offset)
        self.playback_thread=PlaybackThread(self.cap,self.fps,sf,ef);self.playback_thread.new_frame.connect(self.update_frame_display);self.playback_thread.playback_finished.connect(self.on_playback_finished);self.playback_thread.start();self.play_button.setEnabled(False);self.pause_button.setEnabled(True)

    def pause_video(self):
        if self.has_audio:pygame.mixer.music.stop()
        if self.playback_thread:self.playback_thread.stop();self.playback_thread.wait();self.playback_thread=None
        self.play_button.setEnabled(True);self.pause_button.setEnabled(False)

    def on_playback_finished(self):self.pause_video()
    def set_position_from_timeline(self,fi):self.pause_video();self.display_frame(fi)
    def play_from_start_marker(self):sf=self.timeline.get_start();self.timeline.set_playhead(sf);self.pause_video();self.display_frame(sf);self.play_video()
    def update_frame_display(self,fi,fr):self.timeline.set_playhead(fi);self.update_time_label();rgb=cv2.cvtColor(fr,cv2.COLOR_BGR2RGB);h,w,_=rgb.shape;lh,lw=self.video_label.height(),self.video_label.width();s=min(lw/w,lh/h) if w>0 and h>0 else 0;rsz=cv2.resize(rgb,(int(w*s),int(h*s)),interpolation=cv2.INTER_AREA) if s>0 else rgb;h,w,ch=rsz.shape;qi=QImage(rsz.data,w,h,ch*w,QImage.Format.Format_RGB888);px=QPixmap.fromImage(qi);fp=QPixmap(self.video_label.size());fp.fill(Qt.GlobalColor.black);p=QPainter(fp);x,y=(fp.width()-px.width())/2,(fp.height()-px.height())/2;p.drawPixmap(int(x),int(y),px);p.end();self.video_label.setPixmap(fp)
    def display_frame(self,fi):self.cap.set(cv2.CAP_PROP_POS_FRAMES,fi);r,f=self.cap.read();self.update_frame_display(fi,f) if r else None
    def update_time_label(self,_=None):p,s,e=self.timeline.get_playhead(),self.timeline.get_start(),self.timeline.get_end();pt,st,et=(p/self.fps if self.fps>0 else 0),(s/self.fps if self.fps>0 else 0),(e/self.fps if self.fps>0 else 0);fmt=lambda s:f"{int(s//60):02}:{int(s%60):02}";self.time_label.setText(f"{self.tr('play_label')}: {fmt(pt)} | {self.tr('selection_label')}: [{fmt(st)}-{fmt(et)}] | {self.tr('length_label')}: {fmt(self.duration)}")
    def trim_video(self):
        self.pause_video();s,e=(self.timeline.get_start()/self.fps if self.fps>0 else 0),(self.timeline.get_end()/self.fps if self.fps>0 else 0)
        if s>=e:self.status_label.setText(self.tr('status_invalid_range'));return
        f,_=QFileDialog.getSaveFileName(self,self.tr('dialog_save_video'),"",f"{self.tr('dialog_video_files')} (*.mp4 *.avi)")
        if f:self.set_controls_enabled(False);self.progress_bar.setVisible(True);self.progress_bar.setRange(0,0);self.status_label.setText(self.tr('status_trimming'));self.worker=TrimThread(self.input_file,s,e,f,self.tr);self.worker.finished.connect(self.trim_finished);self.worker.start()
        else: self.trim_finished(self.tr('status_trim_cancelled'))
    def trim_finished(self, status_key, result_path):
        self.status_label.setText(self.tr(status_key, path=result_path))
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.set_controls_enabled(True)
        if status_key == 'status_trim_saved':
            self.load_video(fp=result_path)
    def set_controls_enabled(self,e):[getattr(self,w).setEnabled(e) for w in ['load_button','trim_button','timeline','play_button','pause_button']]
    def closeEvent(self,e):self.pause_video();(self.cap.release() if self.cap else None);pygame.mixer.quit();pygame.quit();(os.remove(self.temp_audio_file) if os.path.exists(self.temp_audio_file) else None);e.accept()

if __name__=='__main__':app=QApplication(sys.argv);app.setStyleSheet(DARK_STYLESHEET);editor=VideoEditor();editor.showMaximized();sys.exit(app.exec())
