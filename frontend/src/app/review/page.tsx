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
  const [selectedProvider, setSelectedProvider] = useState<string>("gemini");


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
    fetchExtractions(img.id);
  };

  const fetchExtractions = async (imageId: string) => {
    try {
      const res = await axios.get(`${API_BASE_URL}/extractions/${imageId}`);
      setExtractions(res.data);
      if (res.data.length > 0) {
        setSelectedExtraction(res.data[res.data.length - 1]);
        setGroundTruth(JSON.stringify(res.data[res.data.length - 1].normalized_json, null, 2));
      }
    } catch (err) {
      console.error("Error fetching extractions", err);
    }
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
      const res = await axios.post(`${API_BASE_URL}/validate/${selectedExtraction.extraction_id}`);
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
            <div className="bg-slate-200 rounded-2xl overflow-hidden border border-slate-300 relative group flex items-center justify-center bg-checkered">
              {selectedImage ? (
                <img 
                  src={`${API_BASE_URL}/${selectedImage.file_url}`} 
                  alt="Recibo" 
                  className="max-h-full max-w-full object-contain"
                />
              ) : (
                <p className="text-slate-400 italic">Selecione um recibo</p>
              )}
            </div>


            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
                <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                  <div className="flex items-center gap-4">
                    <span className="text-sm font-bold text-slate-700 uppercase tracking-tight">Extração Automática</span>
                    <select 
                      value={selectedProvider} 
                      onChange={(e) => setSelectedProvider(e.target.value)}
                      className="text-xs border border-slate-300 rounded px-2 py-1 bg-white outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="auto">🔄 Auto (Fallback Chain)</option>
                      <option value="gemini">Google Gemini ✨</option>
                      <option value="mock">Simulador (Mock)</option>
                      <option value="veryfi">Veryfi</option>
                      <option value="mindee">Mindee</option>

                    </select>
                  </div>
                  {selectedImage && (
                    <button 
                      onClick={async () => {
                        setLoading(true);
                        try {
                          const res = await axios.post(`${API_BASE_URL}/extract/${selectedImage.id}?provider=${selectedProvider}`);
                          // Update extraction list
                          fetchExtractions(selectedImage.id);
                        } catch (err) {
                          alert("Erro ao rodar extração. Verifique as chaves de API no backend.");
                        } finally {
                          setLoading(false);
                        }
                      }}
                      disabled={loading}
                      className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-700 flex items-center gap-1.5 font-medium transition-all disabled:opacity-50"
                    >
                      {loading ? <RefreshCw className="animate-spin" size={12} /> : <Play size={12} />}
                      Rodar {selectedProvider.toUpperCase()}
                    </button>
                  )}
               </div>
               
               {/* Extraction History Tabs */}
               {extractions.length > 1 && (
                 <div className="px-4 py-2 border-b border-slate-100 flex gap-2 bg-white overflow-x-auto">
                    {extractions.map((ext, i) => (
                      <button 
                        key={ext.id}
                        onClick={() => {
                          setSelectedExtraction(ext);
                          // We use normalized_json because that's what comes from the backend listing
                          setGroundTruth(JSON.stringify(ext.normalized_json, null, 2));
                        }}
                        className={`text-[10px] px-2 py-1 rounded-full border transition-all whitespace-nowrap ${
                          selectedExtraction?.id === ext.id ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100'
                        }`}
                      >
                        V{i+1} - {ext.provider_id?.split('-')[0] || 'OCR'}
                      </button>
                    ))}
                 </div>
               )}

               <div className="flex-1 p-4 overflow-auto bg-slate-50 text-slate-600">
                  {selectedExtraction ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="p-2 bg-white rounded border border-slate-200">
                          <p className="text-[10px] text-slate-400 font-bold uppercase">Empresa</p>
                          <p className="font-semibold text-slate-800">{selectedExtraction.normalized_json.merchant.name || '---'}</p>
                        </div>
                        <div className="p-2 bg-white rounded border border-slate-200">
                          <p className="text-[10px] text-slate-400 font-bold uppercase">CNPJ</p>
                          <p className="font-semibold text-slate-800">{selectedExtraction.normalized_json.merchant.cnpj || '---'}</p>
                        </div>
                        <div className="p-2 bg-white rounded border border-slate-200">
                          <p className="text-[10px] text-slate-400 font-bold uppercase">Data</p>
                          <p className="font-semibold text-slate-800">{selectedExtraction.normalized_json.document.issue_date || '---'}</p>
                        </div>
                        <div className="p-2 bg-white rounded border border-slate-200">
                          <p className="text-[10px] text-slate-400 font-bold uppercase">Total</p>
                          <p className="font-bold text-indigo-600">R$ {selectedExtraction.normalized_json.payment.total?.toFixed(2) || '0.00'}</p>
                        </div>
                      </div>
                      
                      <div className="p-2 bg-white rounded border border-slate-200">
                        <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Endereço Extraído</p>
                        <p className="text-xs text-slate-700">{selectedExtraction.normalized_json.delivery.address_raw || '---'}</p>
                      </div>

                      <div className="mt-4">
                        <p className="text-[10px] text-slate-400 font-bold uppercase mb-2">Itens ({selectedExtraction.normalized_json.items.length})</p>
                        <div className="space-y-1">
                          {selectedExtraction.normalized_json.items.map((item: any, i: number) => (
                            <div key={i} className="flex justify-between text-[10px] p-1.5 bg-white rounded border border-slate-100">
                              <span className="truncate max-w-[150px]">{item.description}</span>
                              <span className="font-bold">x{item.quantity} - R$ {item.total_price?.toFixed(2)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      <details className="mt-4">
                        <summary className="text-[10px] text-slate-400 font-bold cursor-pointer hover:text-slate-600">Ver JSON Completo</summary>
                        <pre className="mt-2 text-[9px] font-mono bg-slate-100 p-2 rounded overflow-auto max-h-40">
                          {JSON.stringify(selectedExtraction.normalized_json, null, 2)}
                        </pre>
                      </details>
                    </div>
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
