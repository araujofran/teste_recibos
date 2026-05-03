"use client";

import { useState, useEffect } from "react";
import axios from "axios";
import { Check, X, AlertTriangle, Save, Play, RefreshCw, ChevronRight } from "lucide-react";

const API_BASE_URL = "http://localhost:8000";

export default function ReviewPage() {
  const [images, setImages] = useState<any[]>([]);
  const [selectedImage, setSelectedImage] = useState<any>(null);
  const [extractions, setExtractions] = useState<any[]>([]);
  const [selectedExtraction, setSelectedExtraction] = useState<any>(null);
  const [groundTruth, setGroundTruth] = useState<string>("");
  const [validation, setValidation] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchImages();
  }, []);

  const fetchImages = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/images/`);
      setImages(res.data);
    } catch (err) {
      console.error("Error fetching images", err);
    }
  };

  const selectImage = async (img: any) => {
    setSelectedImage(img);
    setSelectedExtraction(null);
    setValidation(null);
    // In a real app, we'd fetch extractions for this image
    // For now, let's assume we trigger a fresh one or list them if we had an endpoint
  };

  const handleValidate = async () => {
    if (!selectedExtraction) return;
    setLoading(true);
    try {
      // 1. Save Ground Truth first
      await axios.post(`${API_BASE_URL}/ground_truth/`, {
        image_id: selectedImage.id,
        manual_json: JSON.parse(groundTruth)
      });

      // 2. Run Validation
      const res = await axios.post(`${API_BASE_URL}/validate/${selectedExtraction.id}`);
      setValidation(res.data);
    } catch (err) {
      alert("Erro na validação. Verifique o formato do JSON de Ground Truth.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-6">
      <header className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Revisão Humana</h1>
          <p className="text-slate-500 mt-1">Compare a extração automática com a verdade de referência.</p>
        </div>
        <div className="flex gap-3">
          <button onClick={fetchImages} className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors">
            <RefreshCw size={20} />
          </button>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-12 gap-6 min-h-0">
        {/* Left Sidebar: Image List */}
        <div className="col-span-3 bg-white rounded-2xl border border-slate-200 overflow-hidden flex flex-col shadow-sm">
          <div className="p-4 border-b border-slate-100 font-semibold text-slate-800 bg-slate-50">
            Recibos Enviados
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {images.map((img) => (
              <button
                key={img.id}
                onClick={() => selectImage(img)}
                className={`w-full text-left p-3 rounded-xl transition-all flex items-center justify-between group ${
                  selectedImage?.id === img.id ? 'bg-indigo-50 border-indigo-100 text-indigo-700' : 'hover:bg-slate-50 text-slate-600'
                }`}
              >
                <div className="truncate">
                  <p className="text-sm font-medium truncate">{img.filename}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{new Date(img.created_at).toLocaleString()}</p>
                </div>
                <ChevronRight size={14} className={`opacity-0 group-hover:opacity-100 transition-opacity ${selectedImage?.id === img.id ? 'opacity-100' : ''}`} />
              </button>
            ))}
          </div>
        </div>

        {/* Center: Image & Editor */}
        <div className="col-span-9 grid grid-rows-2 gap-6">
          {/* Top: Image Preview & JSON Extraction */}
          <div className="grid grid-cols-2 gap-6">
            <div className="bg-slate-200 rounded-2xl overflow-hidden border border-slate-300 relative group flex items-center justify-center">
              {selectedImage ? (
                <div className="text-slate-500 flex flex-col items-center">
                   <p className="text-sm font-medium">Visualização da Imagem</p>
                   <p className="text-xs">{selectedImage.file_url}</p>
                   {/* In a real app: <img src={selectedImage.url} /> */}
                </div>
              ) : (
                <p className="text-slate-400 italic">Selecione um recibo</p>
              )}
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
               <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                  <span className="text-sm font-bold text-slate-700 uppercase tracking-tight">Extração Automática</span>
                  {selectedImage && !selectedExtraction && (
                    <button 
                      onClick={async () => {
                        const res = await axios.post(`${API_BASE_URL}/extract/${selectedImage.id}`);
                        setSelectedExtraction(res.data);
                        // Mock ground truth for easy testing
                        setGroundTruth(JSON.stringify(res.data.normalized, null, 2));
                      }}
                      className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-700 flex items-center gap-1.5 font-medium transition-all"
                    >
                      <Play size={12} /> Rodar OCR
                    </button>
                  )}
               </div>
               <div className="flex-1 p-4 overflow-auto font-mono text-[10px] bg-slate-50 text-slate-600">
                  {selectedExtraction ? (
                    <pre>{JSON.stringify(selectedExtraction.normalized, null, 2)}</pre>
                  ) : (
                    <div className="h-full flex items-center justify-center italic text-slate-400">
                       Aguardando OCR...
                    </div>
                  )}
               </div>
            </div>
          </div>

          {/* Bottom: Ground Truth Editor & Validation Results */}
          <div className="grid grid-cols-2 gap-6">
             <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-indigo-900 text-white">
                  <span className="text-sm font-bold uppercase tracking-tight">Verdade de Referência (Ground Truth)</span>
                  <button 
                    onClick={handleValidate}
                    disabled={!selectedExtraction || loading}
                    className="bg-white text-indigo-900 px-4 py-1.5 rounded-lg text-xs font-bold hover:bg-indigo-50 transition-all flex items-center gap-2 disabled:opacity-50"
                  >
                    {loading ? <RefreshCw className="animate-spin" size={12} /> : <Save size={12} />}
                    Validar & Salvar
                  </button>
                </div>
                <textarea
                  className="flex-1 p-4 font-mono text-[10px] bg-slate-900 text-emerald-400 focus:outline-none resize-none"
                  value={groundTruth}
                  onChange={(e) => setGroundTruth(e.target.value)}
                  placeholder='Cole ou digite aqui o JSON esperado...'
                />
             </div>

             <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 font-bold text-slate-700 bg-slate-50 text-sm uppercase tracking-tight">
                  Resultado da Validação
                </div>
                <div className="flex-1 p-6 overflow-y-auto">
                  {validation ? (
                    <div className="space-y-6">
                      <div className="flex items-center justify-between">
                         <div>
                            <p className="text-xs text-slate-500 uppercase font-bold tracking-wider">Score de Qualidade</p>
                            <p className={`text-4xl font-black ${validation.score >= 90 ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {validation.score.toFixed(1)}%
                            </p>
                         </div>
                         <div className={`px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest ${
                           validation.status === 'approved' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                         }`}>
                           {validation.status === 'approved' ? 'Aprovado' : 'Revisão Necessária'}
                         </div>
                      </div>

                      <div className="space-y-3">
                         <p className="text-xs font-bold text-slate-400 uppercase">Diferenças Encontradas</p>
                         <div className="space-y-2">
                            {Object.entries(validation.metrics.fields).map(([field, data]: any) => (
                              <div key={field} className="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-100">
                                <span className="text-xs font-bold text-slate-600 uppercase">{field}</span>
                                {data.score === 1 ? (
                                  <Check className="text-emerald-500" size={16} />
                                ) : (
                                  <div className="flex items-center gap-2 text-xs text-red-500 font-medium">
                                    <span className="line-through opacity-50">{data.expected}</span>
                                    <X size={14} />
                                    <span>{data.extracted}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                            {validation.metrics.math_errors.map((err: string, i: number) => (
                              <div key={i} className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-100 text-red-700 text-[10px]">
                                <AlertTriangle size={14} className="shrink-0" />
                                <span>{err}</span>
                              </div>
                            ))}
                         </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-slate-300 text-center">
                       <Check size={48} className="mb-4 opacity-10" />
                       <p className="text-sm">Clique em "Validar" para comparar os dados.</p>
                    </div>
                  )}
                </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
