export type AudioRecorderCallbacks = {
    onStart: () => void;
    onStop: (blob: Blob) => void;
    onError: (err: any) => void;
};

export class AudioRecorder {
    private mediaRecorder: MediaRecorder | null = null;
    private audioChunks: Blob[] = [];
    private callbacks: AudioRecorderCallbacks;

    constructor(callbacks: AudioRecorderCallbacks) {
        this.callbacks = callbacks;
    }

    public async toggleRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        } else {
            await this.startRecording();
        }
    }

    private async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => this.audioChunks.push(e.data);
            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.callbacks.onStop(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            this.mediaRecorder.start();
            this.callbacks.onStart();
        } catch (err) {
            this.callbacks.onError(err);
        }
    }
}
