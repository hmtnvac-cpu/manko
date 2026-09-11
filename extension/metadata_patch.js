// Preserve genre/tag metadata collected from Manko pages while keeping the improved translator.
enrichManko=async function(movieId,pageTitle,pageMeta){
  const d=await getJson(`${HEAL}/swx/movie/detail/${encodeURIComponent(movieId)}`);
  const originalTitle=pickDeep(d,['title','name','movieTitle','englishTitle'])||cleanTitle(pageTitle);
  const description=pickDeep(d,['description','overview','synopsis','plot','summary'])||pageMeta.description||'';
  const releaseDate=pageMeta.releaseDate||pickDeep(d,['releaseDate','released','release','date','publishDate'])||'';
  const year=(releaseDate.match(/\b(19|20)\d{2}\b/)||[])[0]||pickDeep(d,['year','releaseYear'])||'';
  const runtime=pageMeta.runtime||pickDeep(d,['runtime','duration','length','movieLength'])||'';
  const studio=pageMeta.studio||pickDeep(d,['studio','maker','label','publisher'])||'';
  const rating=pageMeta.rating||pickDeep(d,['rating','score'])||'';
  const size=pageMeta.size||pickDeep(d,['size','fileSize'])||'';
  const actors=[...new Set((pageMeta.actors||[]).filter(Boolean))];
  const genres=[...new Set((pageMeta.genres||[]).map(x=>String(x).trim()).filter(Boolean))].slice(0,40);
  const snapshots=[...new Set((pageMeta.snapshots||[]).filter(x=>typeof x==='string'&&/^https?:\/\//.test(x)))].slice(0,24);
  const country=pageMeta.country||'Japan',language=pageMeta.language||'Japanese';
  const [titleVi,descriptionVi]=await Promise.all([translateVi(originalTitle),translateVi(description)]);
  return {originalTitle,titleVi,description,descriptionVi,actors,genres,snapshots,code:pageMeta.code||cleanTitle(pageTitle),rating,runtime,size,year,releaseDate,studio,country,countryVi:countryVi(country),language,languageVi:languageVi(language)};
};
