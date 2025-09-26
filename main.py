import sys
import cv2
import ffmpeg
import time
import os
import pygame
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QLabel, 
                             QProgressBar, QStyle)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QPoint, QRect, QTimer, QMutex
from PyQt6.QtGui import QImage, QPixmap, QPainter, QResizeEvent, QMouseEvent, QCursor, QColor, QPen, QBrush, QPolygon

DARK_STYLESHEET = """QWidget{background-color:#2d2d2d;color:#f0f0f0;font-family:Segoe UI;font-size:10pt}QLabel{border:none}QPushButton{background-color:#4a4a4a;border:1px solid #555;padding:5px 10px;border-radius:4px}QPushButton:hover{background-color:#5a5a5a}QPushButton:pressed{background-color:#3a3a3a}QPushButton:disabled{background-color:#404040;color:#888;border-color:#444}QProgressBar{border:1px solid #555;border-radius:4px;text-align:center;background-color:#3d3d3d;color:#f0f0f0}QProgressBar::chunk{background-color:#0078d7;border-radius:3px}"""

class RangeSlider(QWidget):
    start_changed,end_changed,playhead_moved = pyqtSignal(int),pyqtSignal(int),pyqtSignal(int)
    start_drag_finished = pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumHeight(35);self.setCursor(Qt.CursorShape.PointingHandCursor);self._min,self._max,self._start,self._end,self._playhead=0,0,0,0,0;self.dragged_handle=None
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
    def mousePressEvent(self,e:QMouseEvent):p=e.pos().x();s,E=self._v2p(self._start),self._v2p(self._end);self.dragged_handle='start' if abs(p-s)<10 else 'end' if abs(p-E)<10 else 'playhead';self.set_playhead(self._p2v(p));self.playhead_moved.emit(self._playhead)
    def mouseMoveEvent(self,e:QMouseEvent):v=self._p2v(e.pos().x());h=self.dragged_handle; (self.set_start(v),self.start_changed.emit(self._start)) if h=='start' else (self.set_end(v),self.end_changed.emit(self._end)) if h=='end' else (self.set_playhead(v),self.playhead_moved.emit(self._playhead)) if h=='playhead' else None
    def mouseReleaseEvent(self,e:QMouseEvent): self.start_drag_finished.emit() if self.dragged_handle=='start' else None; self.dragged_handle=None

class PlaybackThread(QThread):
    new_frame = pyqtSignal(int, object)
    def __init__(self, cap, fps, start_frame, parent=None):
        super().__init__(parent)
        self.cap, self.fps = cap, fps
        self.current_frame_idx = start_frame
        self.is_running = True
        self.mutex = QMutex()

    def run(self):
        if not self.fps or self.fps == 0: self.is_running = False; return
        frame_duration = 1 / self.fps
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_idx)
        while self.is_running:
            start_time = time.time()
            self.mutex.lock()
            ret, frame = self.cap.read()
            current_idx_copy = self.current_frame_idx
            self.mutex.unlock()
            if not ret: break
            self.new_frame.emit(current_idx_copy, frame)
            self.current_frame_idx += 1
            elapsed = time.time() - start_time
            sleep_time = frame_duration - elapsed
            if sleep_time > 0: time.sleep(sleep_time)

    def seek(self, frame_idx):
        self.mutex.lock()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self.current_frame_idx = frame_idx
        self.mutex.unlock()

    def stop(self): self.is_running = False

class TrimThread(QThread):
    finished=pyqtSignal(str)
    def __init__(self,i,s,e,o):super().__init__();self.i,self.s,self.e,self.o=i,s,e,o
    def run(self):ffmpeg.input(self.i,ss=self.s).output(self.o,to=self.e,vcodec='libx264',acodec='aac').overwrite_output().run(quiet=True);self.finished.emit(f"Видео сохранено в {self.o}")

class VideoEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.cap,self.playback_thread,self.input_file=None,None,None;self.duration,self.fps,self.total_frames=0,0,0;self.temp_audio_file,self.has_audio="temp_audio.wav",False;self.start_time_offset=0.0
        pygame.init();pygame.mixer.init()
        self.sync_timer=QTimer(self);self.sync_timer.setInterval(250);self.sync_timer.timeout.connect(self.sync_playback)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Видеоредактор');self.setGeometry(100,100,800,600);l=QVBoxLayout();self.video_label=QLabel('Загрузите видео');self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.video_label.setStyleSheet("background-color:black;color:#888;font-size:12pt");l.addWidget(self.video_label,1);self.timeline=RangeSlider();self.timeline.playhead_moved.connect(self.set_position_from_timeline);self.timeline.start_changed.connect(self.update_time_label);self.timeline.end_changed.connect(self.update_time_label);self.timeline.start_drag_finished.connect(self.play_from_start_marker);l.addWidget(self.timeline);cl=QHBoxLayout();self.play_button=QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),"");self.play_button.clicked.connect(self.play_video);cl.addWidget(self.play_button);self.pause_button=QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause),"");self.pause_button.clicked.connect(self.pause_video);self.pause_button.setEnabled(False);cl.addWidget(self.pause_button);self.time_label=QLabel("Play: 00:00 | Sel: [00:00-00:00] | Len: 00:00");self.time_label.setStyleSheet("color:#aaa;margin-left:10px");cl.addWidget(self.time_label);cl.addStretch();l.addLayout(cl);bl=QHBoxLayout();self.load_button=QPushButton('Загрузить');self.load_button.clicked.connect(self.load_video);bl.addWidget(self.load_button);bl.addStretch();self.trim_button=QPushButton('Обрезать');self.trim_button.clicked.connect(self.trim_video);self.trim_button.setEnabled(False);self.trim_button.setStyleSheet("background-color:#0078d7;border-color:#005a9e");bl.addWidget(self.trim_button);l.addLayout(bl);self.status_label=QLabel('Готов');self.status_label.setStyleSheet("color:#888;padding:2px");l.addWidget(self.status_label);self.progress_bar=QProgressBar();self.progress_bar.setVisible(False);l.addWidget(self.progress_bar);self.setLayout(l)

    def load_video(self):
        self.pause_video();f,_=QFileDialog.getOpenFileName(self,"Выбрать видео","","Видеофайлы (*.mp4 *.avi *.mkv)");
        if not f:return
        try:
            self.status_label.setText("Загрузка...");QApplication.processEvents();self.input_file=f
            if self.cap:self.cap.release()
            self.cap=cv2.VideoCapture(self.input_file);self.fps=self.cap.get(cv2.CAP_PROP_FPS);self.total_frames=int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT));self.duration=self.total_frames/self.fps if self.fps>0 else 0
            try:ffmpeg.input(self.input_file).output(self.temp_audio_file,format='wav',acodec='pcm_s16le').overwrite_output().run(quiet=True);pygame.mixer.music.load(self.temp_audio_file);self.has_audio=True;self.status_label.setText("Видео и аудио загружены.")
            except ffmpeg.Error:self.has_audio=False;self.status_label.setText("Видео загружено (аудиодорожка отсутствует).")
            self.timeline.set_range(0,self.total_frames-1);self.trim_button.setEnabled(True);self.display_frame(0)
        except Exception as e:self.status_label.setText(f"Ошибка загрузки: {e}")

    def play_video(self):
        if not self.cap or (self.playback_thread and self.playback_thread.isRunning()):return
        start_frame=self.timeline.get_playhead();self.start_time_offset=start_frame/self.fps if self.fps>0 else 0
        if self.has_audio:pygame.mixer.music.play(start=self.start_time_offset)
        self.playback_thread=PlaybackThread(self.cap,self.fps,start_frame);self.playback_thread.new_frame.connect(self.update_frame_display);self.playback_thread.start()
        self.sync_timer.start();self.play_button.setEnabled(False);self.pause_button.setEnabled(True)

    def pause_video(self):
        self.sync_timer.stop()
        if self.has_audio:pygame.mixer.music.pause()
        if self.playback_thread:self.playback_thread.stop();self.playback_thread.wait();self.playback_thread=None
        self.play_button.setEnabled(True);self.pause_button.setEnabled(False)

    def sync_playback(self):
        if not self.playback_thread or not self.playback_thread.isRunning() or not self.has_audio: return
        audio_time=(pygame.mixer.music.get_pos()/1000.0)+self.start_time_offset
        target_frame=int(audio_time*self.fps)
        if abs(target_frame - self.playback_thread.current_frame_idx) > 2: # Порог рассинхронизации
            self.playback_thread.seek(target_frame)
        if target_frame >= self.timeline.get_end(): self.pause_video()

    def set_position_from_timeline(self,frame_idx):self.pause_video();self.display_frame(frame_idx)
    def play_from_start_marker(self):sf=self.timeline.get_start();self.timeline.set_playhead(sf);self.pause_video();self.display_frame(sf);self.play_video()
    def update_frame_display(self,frame_idx,frame):self.timeline.set_playhead(frame_idx);self.update_time_label();rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);h,w,_=rgb.shape;lh,lw=self.video_label.height(),self.video_label.width();s=min(lw/w,lh/h) if w>0 and h>0 else 0;rsz=cv2.resize(rgb,(int(w*s),int(h*s)),interpolation=cv2.INTER_AREA) if s>0 else rgb;h,w,ch=rsz.shape;qi=QImage(rsz.data,w,h,ch*w,QImage.Format.Format_RGB888);px=QPixmap.fromImage(qi);fp=QPixmap(self.video_label.size());fp.fill(Qt.GlobalColor.black);p=QPainter(fp);x,y=(fp.width()-px.width())/2,(fp.height()-px.height())/2;p.drawPixmap(int(x),int(y),px);p.end();self.video_label.setPixmap(fp)
    def display_frame(self,frame_idx):self.cap.set(cv2.CAP_PROP_POS_FRAMES,frame_idx);ret,frame=self.cap.read();self.update_frame_display(frame_idx,frame) if ret else None
    def update_time_label(self,_=None):p,s,e=self.timeline.get_playhead(),self.timeline.get_start(),self.timeline.get_end();pt,st,et=(p/self.fps if self.fps>0 else 0),(s/self.fps if self.fps>0 else 0),(e/self.fps if self.fps>0 else 0);fmt=lambda s:f"{int(s//60):02}:{int(s%60):02}";self.time_label.setText(f"Play: {fmt(pt)} | Sel: [{fmt(st)}-{fmt(et)}] | Len: {fmt(self.duration)}")
    def trim_video(self):self.pause_video();s,e=(self.timeline.get_start()/self.fps if self.fps>0 else 0),(self.timeline.get_end()/self.fps if self.fps>0 else 0);f,_=QFileDialog.getSaveFileName(self,"Сохранить","","Видео (*.mp4 *.avi)");self.set_controls_enabled(False);self.progress_bar.setVisible(True);self.progress_bar.setRange(0,0);self.status_label.setText("Обрезка...");self.worker=TrimThread(self.input_file,s,e,f);self.worker.finished.connect(self.trim_finished);self.worker.start() if f else self.trim_finished("Отменено.")
    def trim_finished(self,m):self.status_label.setText(m);self.progress_bar.setVisible(False);self.progress_bar.setRange(0,100);self.set_controls_enabled(True)
    def set_controls_enabled(self,e):[getattr(self,w).setEnabled(e) for w in ['load_button','trim_button','timeline','play_button','pause_button']]
    def closeEvent(self,e):self.pause_video();(self.cap.release() if self.cap else None);pygame.mixer.quit();pygame.quit();(os.remove(self.temp_audio_file) if os.path.exists(self.temp_audio_file) else None);e.accept()

if __name__=='__main__':app=QApplication(sys.argv);app.setStyleSheet(DARK_STYLESHEET);editor=VideoEditor();editor.show();sys.exit(app.exec())
