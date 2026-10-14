import io
import unittest
import numpy as np
import soundfile as sf
from backend.audio_processing import trim_trailing_silence

class AudioProcessingTest(unittest.TestCase):
    rate=24000
    def encode(self,a):
        b=io.BytesIO();sf.write(b,a,self.rate,format='WAV',subtype='PCM_16');return b.getvalue()
    def tone(self,seconds,volume=.1):
        return volume*np.sin(np.arange(round(seconds*self.rate))*2*np.pi*220/self.rate)
    def test_long_codec_noise_tail_is_trimmed(self):
        speech=self.tone(6);noise=self.tone(75,.00014)
        noise[-10:]=.0012
        cleaned,trimmed=trim_trailing_silence(self.encode(np.r_[speech,noise]))
        self.assertAlmostEqual(sf.info(io.BytesIO(cleaned)).duration,6.35,places=2)
        self.assertAlmostEqual(trimmed,74.65,places=2)
        np.testing.assert_array_equal(sf.read(io.BytesIO(cleaned))[0][:len(speech)],sf.read(io.BytesIO(self.encode(speech)))[0])
    def test_internal_and_leading_pauses_remain(self):
        raw=self.encode(np.r_[np.zeros(self.rate),self.tone(1),np.zeros(self.rate*3),self.tone(1),np.zeros(self.rate*3)])
        clean,_=trim_trailing_silence(raw)
        self.assertAlmostEqual(sf.info(io.BytesIO(clean)).duration,6.35,places=2)
    def test_short_tail_unchanged(self):
        raw=self.encode(np.r_[self.tone(2),np.zeros(self.rate)])
        self.assertEqual(trim_trailing_silence(raw),(raw,0.0))
    def test_quiet_speech_and_stereo_preserved(self):
        signal=np.r_[self.tone(2,.0005),np.zeros(self.rate*3)]
        raw=self.encode(np.stack([signal,-signal],axis=1));clean,_=trim_trailing_silence(raw)
        self.assertAlmostEqual(sf.info(io.BytesIO(clean)).duration,2.35,places=2)
        self.assertEqual(sf.info(io.BytesIO(clean)).channels,2)
    def test_all_zero_unchanged(self):
        raw=self.encode(np.zeros(self.rate*4));self.assertEqual(trim_trailing_silence(raw),(raw,0.0))
