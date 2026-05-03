"use client";

import { useState } from "react";
import axios from "axios";
import { Upload, FileText, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

const API_BASE_URL = "http://localhost:8000";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadRes = await axios.post(`${API_BASE_URL}/upload/`, formData);
      const imageId = uploadRes.data.image_id;
      
      setExtracting(true);
      const extractRes = await axios.post(`${API_BASE_URL}/extract/${imageId}?provider=mock`);
      
      setResult(extractRes.data.normalized);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao processar imagem.");
    } finally {
      setLoading(false);
      setExtracting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Laboratório de Extração</h1>
        <p className="text-slate-500 mt-2">Envie uma foto de recibo para testar o motor de OCR e normalização.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Upload Card */}
        <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm">
          <div 
            className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
              file ? 'border-indigo-200 bg-indigo-50' : 'border-slate-200 hover:border-indigo-300'
            }`}
          >
            <input 
              type="file" 
              id="receipt-upload" 
              className="hidden" 
              onChange={handleFileChange}
              accept="image/*"
            />
            <label htmlFor="receipt-upload" className="cursor-pointer">
              <div className="bg-indigo-100 text-indigo-600 p-4 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <Upload size={24} />
              </div>
              <p className="text-slate-700 font-medium">{file ? file.name : "Clique para selecionar ou arraste"}</p>
              <p className="text-slate-400 text-sm mt-1">PNG, JPG ou JPEG</p>
            </label>
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full mt-6 bg-slate-900 text-white py-3 px-6 rounded-xl font-semibold hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin" size={20} />
                {extracting ? "Extraindo Dados..." : "Enviando..."}
              </>
            ) : (
              <>
                <FileText size={20} />
                Iniciar Extração
              </>
            )}
          </button>

          {error && (
            <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-lg flex items-start gap-3 text-sm border border-red-100">
              <AlertCircle size={18} className="shrink-0 mt-0.5" />
              <p>{error}</p>
            </div>
          )}
        </div>

        {/* Result Preview */}
        <div className="bg-slate-900 rounded-2xl p-6 text-slate-300 font-mono text-xs overflow-hidden flex flex-col shadow-xl">
          <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-4">
            <span className="text-slate-500 uppercase tracking-widest font-bold">Standard JSON Output</span>
            {result && <CheckCircle2 className="text-emerald-400" size={16} />}
          </div>
          <div className="flex-1 overflow-auto custom-scrollbar">
            {result ? (
              <pre>{JSON.stringify(result, null, 2)}</pre>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-slate-600 text-center p-8">
                <FileText size={48} className="mb-4 opacity-20" />
                <p>Aguardando processamento...</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
