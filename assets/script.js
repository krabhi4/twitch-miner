var options = {
    series: [],
    chart: {
        type: 'area',
        stacked: false,
        height: 460,
        zoom: { type: 'x', enabled: true, autoScaleYaxis: true },
        foreColor: '#9ca3af',
        toolbar: { autoSelected: 'zoom' }
    },
    dataLabels: { enabled: false },
    stroke: { curve: 'smooth', width: 2 },
    markers: { size: 0 },
    title: { text: 'Channel points (UTC)', align: 'left' },
    colors: ["#9146ff","#00c7b7","#e0af68","#ff5c8d","#3b82f6","#10b981"],
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, inverseColors: false, opacityFrom: 0.5, opacityTo: 0, stops: [0, 90, 100] } },
    yaxis: { title: { text: 'Channel points' }, labels: { formatter: v => millify(v) } },
    xaxis: { type: 'datetime', labels: { datetimeUTC: false } },
    tooltip: {
        theme: 'dark',
        shared: false,
        x: { show: true, format: 'HH:mm:ss dd MMM yyyy' },
        custom: ({series, seriesIndex, dataPointIndex, w}) => {
            const z = w.globals.seriesZ && w.globals.seriesZ[seriesIndex] ? (w.globals.seriesZ[seriesIndex][dataPointIndex] || '') : '';
            const title = escapeHtml(w.globals.seriesNames[seriesIndex] || '');
            const reason = escapeHtml(z);
            const points = series[seriesIndex] ? series[seriesIndex][dataPointIndex] : '';
            return `<div class="apexcharts-active"><div class="apexcharts-tooltip-title">${title}</div><div class="apexcharts-tooltip-series-group apexcharts-active" style="order:1;display:flex;padding-bottom:0px !important;"><div class="apexcharts-tooltip-text"><div class="apexcharts-tooltip-y-group"><span class="apexcharts-tooltip-text-label"><b>Points</b>: ${points}</span><br><span class="apexcharts-tooltip-text-label"><b>Reason</b>: ${reason}</span></div></div></div></div>`;
        }
    },
    noData: { text: 'No data – select a streamer' },
    grid: { borderColor: 'rgba(255, 255, 255, 0.08)' }
};
const chart = new ApexCharts(document.querySelector("#chart"), options);
let currentStreamer = null;
let annotations = [];
let streamersList = [];
let streamersDetails = [];
let sortBy = "Points descending";
let sortField = 'points';
let defaultDays = (typeof daysAgo !== 'undefined' && !isNaN(daysAgo)) ? daysAgo : 7;
let startDate = new Date(); startDate.setDate(startDate.getDate() - defaultDays);
let endDate = new Date();
let compareMode = false;
let selectedCompare = new Set();
let historyRows = [];
let historyFiltered = [];
let historyPage = 1;
let historyPageSize = 25;
let historySortField = 'x';
let historySortAsc = false;
let enumsCache = null;

function escapeHtml(s){ if(s === null || s === undefined) return ''; return String(s).replace(/[&<>"']/g, c=> ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function jsArg(s){ return escapeHtml(JSON.stringify(String(s))); }
function millify(n){ if(n==null) return '-'; if(n>=1000000) return (n/1000000).toFixed(1)+'M'; if(n>=1000) return (n/1000).toFixed(1)+'k'; return String(n); }
function formatDate(d){ const dd=new Date(d); const m=''+(dd.getMonth()+1), day=''+dd.getDate(), y=dd.getFullYear(); return [y, m.padStart(2,'0'), day.padStart(2,'0')].join('-'); }
function formatDateTime(ts){ return new Date(ts).toLocaleString(); }

$(document).ready(function(){
    chart.render();
    if(!localStorage.getItem("annotations")) localStorage.setItem("annotations", true);
    if(!localStorage.getItem("dark-mode")) localStorage.setItem("dark-mode", true);
    if(!localStorage.getItem("sort-by")) localStorage.setItem("sort-by", "Points descending");
    if(!localStorage.getItem("compare-mode")) localStorage.setItem("compare-mode", false);

    $('#annotations').prop("checked", localStorage.getItem("annotations")==="true");
    $('#dark-mode').prop("checked", localStorage.getItem("dark-mode")==="true");
    compareMode = localStorage.getItem("compare-mode")==="true";
    $('#compare-mode').prop("checked", compareMode);
    sortBy = localStorage.getItem("sort-by");
    if(sortBy.includes("Points")) sortField='points';
    else if(sortBy.includes("Gained")) sortField='total_gained';
    else if(sortBy.includes("Last activity")) sortField='last_activity';
    else sortField='name';
    $('#sorting-by').text(sortBy);
    $('#startDate').val(formatDate(startDate));
    $('#endDate').val(formatDate(endDate));

    $('.tab-btn').click(function(){
        const t=$(this).data('tab');
        $('.tab-btn').removeClass('active'); $(this).addClass('active');
        $('.tab-pane').removeClass('active'); $('#tab-'+t).addClass('active');
        if(t==='dashboard'){ if(chartDirty){ chartDirty=false; refreshChart(); } else { chart.updateOptions({}, true, false); updateAnnotations(); } }
        if(t==='history' && historyRows.length===0) loadHistory();
        if(t==='config') loadConfig();
    });

    localStorage.removeItem('headerVisibility');
    $('#header').show();

    $('#annotations').click(()=>{ localStorage.setItem("annotations", $('#annotations').prop("checked")); updateAnnotations(); });
    $('#dark-mode').click(()=> toggleDarkMode());
    $('#compare-mode').change(function(){ compareMode=this.checked; localStorage.setItem("compare-mode", compareMode); selectedCompare.clear(); if(compareMode && currentStreamer) selectedCompare.add(currentStreamer.replace('.json','')); updateCompareUI(); if(currentStreamer) changeStreamer(currentStreamer, 1); });
    $('.preset-btn').click(function(){ $('.preset-btn').removeClass('active'); $(this).addClass('active'); const d=$(this).data('days'); if(d==='all'){ $('#startDate').val(''); $('#endDate').val(formatDate(new Date())); startDate=new Date(0); endDate=new Date(); } else { const n=parseInt(d); startDate=new Date(); startDate.setDate(startDate.getDate()-n); endDate=new Date(); $('#startDate').val(formatDate(startDate)); $('#endDate').val(formatDate(endDate)); } if(currentStreamer) refreshChart(); });
    $('#startDate').change(()=>{ const v=$('#startDate').val(); if(v) startDate=new Date(v); if(currentStreamer) refreshChart(); });
    $('#endDate').change(()=>{ const v=$('#endDate').val(); if(v) endDate=new Date(v); if(currentStreamer) refreshChart(); });
    $('#agg-select').change(()=>{ if(currentStreamer) refreshChart(); });
    $('#btn-export').click(exportCSV);
    $('#btn-reset-zoom').click(()=> chart.resetSeries(true,true));
    $('#streamer-search').on('input', renderStreamers);
    $('#btn-history-refresh').click(loadHistory);
    $('#history-streamer-filter').change(loadHistory);
    $('#history-type-filter').change(applyHistoryFilters);
    $('#history-search').on('input', applyHistoryFilters);
    $('.history-table th[data-sort]').click(function(){ const f=$(this).data('sort'); if(historySortField===f) historySortAsc=!historySortAsc; else {historySortField=f; historySortAsc=true;} applyHistoryFilters(); });
    $('#btn-save-global').click(saveGlobalConfig);
    $('#btn-add-streamer').click(addStreamer);
    $('#new-streamer-name').on('keypress', function(e){
        if(e.which === 13){
            e.preventDefault();
            addStreamer();
        }
    });
    $('#btn-save-priority').click(savePriority);

    toggleDarkMode();
    loadOverview();
    getStreamers();

    var isLogChecked = localStorage.getItem('logCheckboxState')==='true';
    $('#log').prop('checked', isLogChecked);
    if(isLogChecked) { $('#log-box').show(); startLogPoll(); }
    $('#log').change(function(){
        const c=$(this).prop('checked');
        localStorage.setItem('logCheckboxState', c);
        if(c){
            $('#log-box').show();
            startLogPoll();
        } else {
            $('#log-box').hide();
            if(logTimer) { clearTimeout(logTimer); logTimer = null; }
        }
    });

    updateAnnotations();
    if(refresh > 0) setInterval(()=>{ loadOverview(); refreshChart(); }, refresh);
});

function refreshChart(){ if(compareMode && selectedCompare.size) loadCompareChart(); else if(currentStreamer) getStreamerData(currentStreamer); }

function loadOverview(){
    $.getJSON('/api/overview', function(data){
        $('#stat-streamers').text(data.total_streamers);
        $('#stat-points').text(millify(data.total_points));
        $('#stat-gained').text(millify(data.total_gained));
        $('#stat-winrate').text(data.win_rate);
    });
    $.getJSON('/api/streamers/details', function(data){
        streamersDetails = data;
    });
}

function reloadAfterPrune(){
    if(!currentStreamer && !selectedCompare.size){ chartGen++; options.title.text='Channel points (UTC)'; chart.updateOptions({ title: options.title }); chart.updateSeries([]); clearAnnotations(); annotations=[]; $('#chart-title').text('Select a streamer'); $('#chart-stats,#gain-breakdown').empty(); return; }
    refreshChart();
}

function rebuildHistoryFilter(names){
    const sel=$('#history-streamer-filter'); const prev=sel.val(); sel.find('option:not(:first)').remove();
    names.forEach(n=> sel.append(`<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`));
    sel.val(prev); if(sel.val()!==prev){ sel.val(''); loadHistory(); }
}

function pruneStale(){
    const live=new Set(streamersList.map(s=>s.displayName||s.name.replace('.json','')));
    let stale=false;
    selectedCompare.forEach(n=>{ if(!live.has(n)){ selectedCompare.delete(n); stale=true; } });
    if(currentStreamer && !live.has(currentStreamer.replace('.json',''))){ currentStreamer = compareMode && selectedCompare.size ? [...selectedCompare][0]+'.json' : null; stale=true; }
    return stale;
}

let streamersGen=0;
function getStreamers(){
    const gen=++streamersGen;
    $.getJSON('/api/streamers/details', function(response){
        if(gen!==streamersGen) return;
        if(!response || response.length===0){
            $.getJSON('streamers', function(simple){
                if(gen!==streamersGen) return;
                streamersList = simple.map(s=>({name:s.name, points:s.points, last_activity:s.last_activity, total_gained:0}));
                const stale=pruneStale(); sortStreamers(); renderStreamers(); if(stale) reloadAfterPrune();
                rebuildHistoryFilter(simple.map(s=>s.name.replace('.json','')));
            });
            return;
        }
        streamersDetails = response;
        streamersList = response.map(d=>({ name: d.file || d.name+'.json', displayName: d.name, points: d.points, last_activity: d.last_activity, total_gained: d.total_gained, is_online: d.is_online, bets: d.bets }));
        const stale=pruneStale();
        sortStreamers();
        renderStreamers();
        if(stale) reloadAfterPrune();
        rebuildHistoryFilter(response.map(d=>d.name));
    });
}

function renderStreamers(){
    const query = ($('#streamer-search').val()||'').toLowerCase();
    let filtered = streamersList.filter(s=> !query || s.displayName?.toLowerCase().includes(query) || s.name.toLowerCase().includes(query));
    $("#streamers-list").empty();
    $("#streamer-count").text(filtered.length);
    let idx=1;
    filtered.forEach((streamer)=>{
        const name = streamer.displayName || streamer.name.replace(".json","");
        const isActive = currentStreamer === streamer.name;
        let display = escapeHtml(name);
        if(sortField==='points') display = `<span class="points">${millify(streamer.points)}</span> ${escapeHtml(name)}`;
        else if(sortField==='total_gained') display = `<span class="points">+${millify(streamer.total_gained)}</span> ${escapeHtml(name)}`;
        else if(sortField==='last_activity') display = `<span class="meta">${formatDate(streamer.last_activity)}</span> ${escapeHtml(name)}`;
        if(streamer.is_online) display = `<span class="dot online" title="Online"></span> `+display;
        else if(streamer.is_online===false) display = `<span class="dot offline" title="Offline"></span> `+display;
        const activeClass = isActive ? 'is-active' : '';
        const compareChecked = selectedCompare.has(name) ? 'checked' : '';
        const checkbox = compareMode ? `<input type="checkbox" class="compare-check" data-name="${escapeHtml(name)}" ${compareChecked} style="margin-right:6px">` : '';
        const wrBadge = (streamer.bets && streamer.bets.placed > 0) ? `<span class="meta" style="margin-left:auto">${streamer.bets.win_rate}% WR</span>` : '';
        const li = `<li class="${activeClass}"><a onClick="handleStreamerClick(${jsArg(streamer.name)}, ${jsArg(name)}); return false;">${checkbox}${display}${wrBadge}</a></li>`;
        $("#streamers-list").append(li);
        idx++;
    });
    if(!currentStreamer && filtered.length>0){
        const saved = localStorage.getItem("selectedStreamer");
        const exists = filtered.find(s=> s.name===saved);
        const target = exists ? saved : filtered[0].name;
        const targetDisplay = filtered.find(s=> s.name===target).displayName || target.replace(".json","");
        changeStreamer(target, 1);
    }
    $('.compare-check').change(function(e){
        e.stopPropagation();
        const nm=$(this).attr('data-name');
        if(this.checked) selectedCompare.add(nm); else selectedCompare.delete(nm);
        if(selectedCompare.size===0 && currentStreamer) selectedCompare.add(currentStreamer.replace(".json",""));
        loadCompareChart();
    });
}

function handleStreamerClick(file, displayName){
    if(compareMode){
        if(selectedCompare.has(displayName)) selectedCompare.delete(displayName); else selectedCompare.add(displayName);
        if(selectedCompare.size===0) selectedCompare.add(displayName);
        currentStreamer=file;
        localStorage.setItem("selectedStreamer", file);
        renderStreamers();
        loadCompareChart();
    } else {
        changeStreamer(file, 1);
    }
}
function updateCompareUI(){ renderStreamers(); }

function sortStreamers(){
    streamersList = streamersList.sort((a,b)=>{
        let av=a[sortField], bv=b[sortField];
        if(sortField==='name') { av=(a.displayName||a.name).toLowerCase(); bv=(b.displayName||b.name).toLowerCase(); }
        let cmp = av > bv ? 1 : av < bv ? -1 : 0;
        return cmp * (sortBy.includes("ascending") ? 1 : -1);
    });
}
function changeSortBy(option){
    sortBy = option.innerText.trim();
    if(sortBy.includes("Points")) sortField='points';
    else if(sortBy.includes("Gained")) sortField='total_gained';
    else if(sortBy.includes("Last activity")) sortField='last_activity';
    else sortField='name';
    sortStreamers(); renderStreamers();
    $('#sorting-by').text(sortBy);
    localStorage.setItem("sort-by", sortBy);
}

function changeStreamer(streamer, index){
    $("#streamers-list li").removeClass("is-active");
    currentStreamer = streamer;
    options.title.text = `${streamer.replace(".json","")}'s channel points (UTC)`;
    chart.updateOptions({ title: options.title }); $('#chart-title').text(options.title.text);
    localStorage.setItem("selectedStreamer", currentStreamer);
    if(compareMode && selectedCompare.size===0) selectedCompare.add(streamer.replace('.json',''));
    refreshChart();
    updateChartStats(streamer);
    renderStreamers();
}

let chartGen=0, chartDirty=false;
function getStreamerData(streamer){
    if(!streamer) return;
    if(!$('#chart').is(':visible')){ chartDirty=true; return; }
    const gen=++chartGen;
    const freq = $('#agg-select').val();
    const params = { startDate: $('#startDate').val() || formatDate(startDate), endDate: $('#endDate').val() || formatDate(endDate) };
    const url = freq && freq!=='raw' ? `./api/series/${streamer}?freq=${freq}` : `./json/${streamer}`;
    $.getJSON(url, params, function(response){
        if(gen!==chartGen) return;
        if(response.error){ chart.updateSeries([{name: streamer.replace(".json",""), data:[]} ]); return; }
        if(compareMode && selectedCompare.size>1) return; // compare will override
        chart.updateSeries([{ name: streamer.replace(".json",""), data: response["series"] }], true);
        clearAnnotations();
        annotations = response["annotations"] || [];
        updateAnnotations();
        const series = response["series"] || [];
        if(series.length>0){
            const first = series[0].y, last = series[series.length-1].y;
            const gained = last - first;
            $('#chart-stats').html(`<span class="stat-chip">Points: ${millify(last)}</span><span class="stat-chip">Gained: +${millify(gained)}</span><span class="stat-chip">Samples: ${series.length}</span>`);
            const zCounts = {}; series.forEach(s=>{ const z=s.z||'Unknown'; zCounts[z]=(zCounts[z]||0)+1; });
            let html='';
            for(const k in zCounts){ html+=`<div class="gain-card"><b>${escapeHtml(k)}</b><br>${zCounts[k]} events</div>`; }
            $('#gain-breakdown').html(html);
        } else {
            $('#chart-stats').html('<span class="stat-chip">No data in range</span>');
            $('#gain-breakdown').empty();
        }
    });
}

function loadCompareChart(){
    if(!compareMode || selectedCompare.size===0) return;
    if(!$('#chart').is(':visible')){ chartDirty=true; return; }
    const gen=++chartGen;
    const freq = $('#agg-select').val();
    const params = { startDate: $('#startDate').val() || formatDate(startDate), endDate: $('#endDate').val() || formatDate(endDate) };
    chart.updateSeries([]); clearAnnotations(); annotations = [];
    if(currentStreamer && !selectedCompare.has(currentStreamer.replace('.json',''))){ currentStreamer = Array.from(selectedCompare).pop()+'.json'; localStorage.setItem("selectedStreamer", currentStreamer); renderStreamers(); }
    let promises = [];
    selectedCompare.forEach(name=>{
        const file = name+'.json';
        const url = freq && freq!=='raw' ? `./api/series/${file}?freq=${freq}` : `./json/${file}`;
        promises.push($.getJSON(url, params).then(res=> ({name, data: res.series || []})));
    });
    Promise.all(promises).then(results=>{
        if(gen!==chartGen) return;
        const series = results.map(r=> ({name: r.name, data: r.data}));
        chart.updateSeries(series, true);
        options.title.text = `Compare: ${Array.from(selectedCompare).join(', ')}`;
        chart.updateOptions({ title: options.title }); $('#chart-title').text(options.title.text);
        $('#chart-stats').html(`<span class="stat-chip">Comparing ${selectedCompare.size} streamers</span>`);
        $('#gain-breakdown').html('');
    });
}

function updateChartStats(streamer){
    const detail = streamersDetails.find(d=> d.name===streamer.replace(".json",""));
    if(detail){
        const b=detail.bets||{};
        $('#chart-stats').html(`<span class="stat-chip">Bets: ${b.placed||0}</span><span class="stat-chip">Wins: ${b.wins||0}</span><span class="stat-chip">WR: ${b.win_rate||0}%</span>`);
    }
}

function updateAnnotations(){
    clearAnnotations();
    if($('#annotations').prop("checked") && $('#chart').is(':visible') && annotations) annotations.forEach((ann,idx)=>{ ann.id=`id-${idx}`; chart.addXaxisAnnotation(ann,true); });
}
function clearAnnotations(){ if(annotations) annotations.forEach((a,i)=>{ try{chart.removeAnnotation(a.id||`id-${i}`)}catch(e){}}); chart.clearAnnotations(); }

let lastReceivedLogIndex=0, autoUpdateLog=true, logTimer=null, logFailCount=0, logGen=0, logHint=false;
function startLogPoll(){
    if(logTimer) { clearTimeout(logTimer); logTimer = null; }
    lastReceivedLogIndex = 0;
    logFailCount = 0;
    $('#log-content').text('');
    logHint = false;
    logGen++;
    pollLog();
}
function pollLog(){
    if(!$('#log').prop("checked")) return;
    const gen = logGen;
    $.ajax({
        url: `/log?lastIndex=${lastReceivedLogIndex}`,
        type: 'GET',
        dataType: 'text',
        success: function(data, textStatus, xhr){
            if(gen !== logGen) return;
            logFailCount = 0;
            const offsetHeader = xhr.getResponseHeader('X-Log-Offset');
            if (offsetHeader !== null) {
                lastReceivedLogIndex = parseInt(offsetHeader, 10);
            } else {
                lastReceivedLogIndex += data.length;
            }
            if (data) {
                const el = $("#log-content");
                if(logHint){ el.text(''); logHint=false; }
                let cur = el.text() + data;
                if (cur.length > 200000) {
                    cur = cur.slice(-100000);
                }
                el.text(cur);
                el.scrollTop(el[0].scrollHeight);
            }
            if(autoUpdateLog && $('#log').prop("checked")) {
                logTimer = setTimeout(pollLog, 1500);
            }
        },
        error: function(xhr){
            if(gen !== logGen) return;
            if(xhr.status===404 && !$('#log-content').text()){ $('#log-content').text('Enable save=True in logger_settings to view live log stream.'); logHint=true; }
            logFailCount++;
            const backoff = Math.min(30000, 2000 * Math.pow(1.5, logFailCount));
            if(autoUpdateLog && $('#log').prop("checked")) {
                logTimer = setTimeout(pollLog, backoff);
            }
        }
    });
}
$('#auto-update-log').click(()=>{
    autoUpdateLog=!autoUpdateLog;
    $('#auto-update-log').text(autoUpdateLog ? '⏸️ Pause' : '▶️ Resume');
    if(autoUpdateLog){ if(logTimer) clearTimeout(logTimer); logGen++; pollLog(); }
});

function exportCSV(){
    if(!currentStreamer) return;
    const series = chart.w.globals.series[0] ? chart.w.globals.series[0] : [];
    $.getJSON(`./json/${currentStreamer}`, {startDate: $('#startDate').val(), endDate: $('#endDate').val()}, function(res){
        let csv='x,y,z\n';
        (res.series||[]).forEach(r=>{ csv+=`${new Date(r.x).toISOString()},${r.y},"${r.z}"\n`; });
        const blob=new Blob([csv],{type:'text/csv'});
        const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`${currentStreamer.replace('.json','')}_points.csv`; a.click();
    });
}

let histGen=0;
function loadHistory(){
    const gen=++histGen;
    const streamer = $('#history-streamer-filter').val();
    const params = {};
    if(streamer) params.streamer=streamer;
    params.limit=500;
    $.getJSON('/api/bets', params, function(data){
        if(gen!==histGen) return;
        historyRows = data;
        applyHistoryFilters();
        const wins = data.filter(r=>r.type==='WIN').length;
        const losses = data.filter(r=>r.type==='LOSE').length;
        const placed = data.filter(r=>r.type==='BET_PLACED').length;
        const streaks = data.filter(r=>r.type==='WATCH_STREAK').length;
        const wr = wins+losses>0 ? ((wins/(wins+losses))*100).toFixed(1) : 0;
        $('#history-summary').html(`<span class="stat-chip">Bets: ${placed}</span><span class="stat-chip" style="color:#36b535">Wins: ${wins}</span><span class="stat-chip" style="color:#ff4545">Losses: ${losses}</span><span class="stat-chip">WR: ${wr}%</span><span class="stat-chip">Streaks: ${streaks}</span>`);
    });
}
function applyHistoryFilters(){
    const type = $('#history-type-filter').val();
    const streamer = $('#history-streamer-filter').val();
    const q = ($('#history-search').val()||'').toLowerCase();
    historyFiltered = historyRows.filter(r=>{
        if(type && r.type!==type) return false;
        if(streamer && r.streamer!==streamer) return false;
        if(q && ! (r.text.toLowerCase().includes(q) || r.streamer.toLowerCase().includes(q) || r.type.toLowerCase().includes(q))) return false;
        return true;
    });
    historyFiltered.sort((a,b)=>{
        let av=a[historySortField], bv=b[historySortField];
        if(historySortField==='datetime') { av=a.x; bv=b.x; }
        if(av===bv) return 0;
        const cmp = av > bv ? 1 : -1;
        return historySortAsc ? cmp : -cmp;
    });
    historyPage=1;
    renderHistoryTable();
}
function renderHistoryTable(){
    const tbody=$('#history-body'); tbody.empty();
    if(historyFiltered.length===0){ tbody.append('<tr><td colspan="5" class="empty">No records</td></tr>'); $('#history-pagination').empty(); return; }
    const totalPages=Math.ceil(historyFiltered.length/historyPageSize);
    if(historyPage>totalPages) historyPage=totalPages;
    const start=(historyPage-1)*historyPageSize;
    const pageRows=historyFiltered.slice(start, start+historyPageSize);
    pageRows.forEach(r=>{
        const safeType = escapeHtml(r.type);
        const badge = `<span class="badge-type ${safeType}">${safeType}</span>`;
        const bal = (r.balance !== null && r.balance !== undefined) ? millify(r.balance) : '-';
        const dateStr = r.datetime ? new Date(r.x).toLocaleString() : '-';
        tbody.append(`<tr><td>${escapeHtml(dateStr)}</td><td>${escapeHtml(r.streamer)}</td><td>${badge}</td><td>${escapeHtml(r.text)}</td><td>${escapeHtml(bal)}</td></tr>`);
    });
    let pagHtml='';
    for(let i=1;i<=totalPages;i++){ pagHtml+=`<button class="btn-small ${i===historyPage?'active':''}" onclick="goHistoryPage(${i})">${i}</button>`; }
    $('#history-pagination').html(pagHtml);
}
function goHistoryPage(p){ historyPage=p; renderHistoryTable(); }

function loadConfig(channelsOnly){
    return $.getJSON('/api/enums').then(function(enums){ enumsCache=enums; return $.getJSON('/api/config'); }).then(function(cfg){
        if(cfg && cfg.can_add_streamer === false){
            $('.add-streamer-row').remove();
        }
        if(!channelsOnly) renderGlobalConfig(cfg.global, cfg.priority);
        renderPerChannel(cfg.streamers);
        if(!channelsOnly) renderPriority(cfg.priority);
    });
}
function renderGlobalConfig(global, priority){
    const c=$('#global-config-form'); c.empty();
    if(!global) { c.html('<p class="empty">No config</p>'); return; }
    const bet=global.bet||{};
    const fc=bet.filter_condition||{};
    c.html(`
        <div class="form-grid">
            <div class="form-group"><label>Make predictions</label><select id="g_make_predictions"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Follow raid</label><select id="g_follow_raid"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Claim drops</label><select id="g_claim_drops"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Claim moments</label><select id="g_claim_moments"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Watch streak</label><select id="g_watch_streak"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Community goals</label><select id="g_community_goals"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Chat presence</label><select id="g_chat"></select></div>
        </div>
        <h4 style="margin:10px 0 6px">Bet Settings</h4>
        <div class="form-grid">
            <div class="form-group"><label>Strategy</label><select id="g_strategy"></select></div>
            <div class="form-group"><label>Percentage %</label><input id="g_percentage" type="number" min="1" max="100"></div>
            <div class="form-group"><label>Percentage gap</label><input id="g_percentage_gap" type="number"></div>
            <div class="form-group"><label>Max points</label><input id="g_max_points" type="number"></div>
            <div class="form-group"><label>Minimum points</label><input id="g_minimum_points" type="number"></div>
            <div class="form-group"><label>Stealth mode</label><select id="g_stealth_mode"><option value="true">True</option><option value="false">False</option></select></div>
            <div class="form-group"><label>Delay mode</label><select id="g_delay_mode"></select></div>
            <div class="form-group"><label>Delay</label><input id="g_delay" type="number" step="0.1"></div>
            <div class="form-group"><label>Filter by</label><select id="g_filter_by"><option value="">None</option></select></div>
            <div class="form-group"><label>Where</label><select id="g_filter_where"><option value="">-</option></select></div>
            <div class="form-group"><label>Value</label><input id="g_filter_value" type="number" step="any"></div>
        </div>
    `);
    if(enumsCache){
        $('#g_chat').html(enumsCache.chat_presences.map(v=>`<option value="${v}">${v}</option>`).join(''));
        $('#g_strategy').html(enumsCache.strategies.map(v=>`<option value="${v}">${v}</option>`).join(''));
        $('#g_delay_mode').html(enumsCache.delay_modes.map(v=>`<option value="${v}">${v}</option>`).join(''));
        $('#g_filter_by').html('<option value="">None</option>'+enumsCache.outcome_keys.map(v=>`<option value="${v}">${v}</option>`).join(''));
        $('#g_filter_where').html('<option value="">-</option>'+enumsCache.conditions.map(v=>`<option value="${v}">${v}</option>`).join(''));
    }
    $('#g_make_predictions').val(String(global.make_predictions));
    $('#g_follow_raid').val(String(global.follow_raid));
    $('#g_claim_drops').val(String(global.claim_drops));
    $('#g_claim_moments').val(String(global.claim_moments));
    $('#g_watch_streak').val(String(global.watch_streak));
    $('#g_community_goals').val(String(global.community_goals));
    $('#g_chat').val(global.chat);
    $('#g_strategy').val(bet.strategy);
    $('#g_percentage').val(bet.percentage);
    $('#g_percentage_gap').val(bet.percentage_gap);
    $('#g_max_points').val(bet.max_points);
    $('#g_minimum_points').val(bet.minimum_points);
    $('#g_stealth_mode').val(String(bet.stealth_mode));
    $('#g_delay_mode').val(bet.delay_mode);
    $('#g_delay').val(bet.delay);
    if(fc && fc.by){ $('#g_filter_by').val(fc.by); $('#g_filter_where').val(fc.where); $('#g_filter_value').val(fc.value); }
}
function saveGlobalConfig(){
    const global={
        make_predictions: $('#g_make_predictions').val()==='true',
        follow_raid: $('#g_follow_raid').val()==='true',
        claim_drops: $('#g_claim_drops').val()==='true',
        claim_moments: $('#g_claim_moments').val()==='true',
        watch_streak: $('#g_watch_streak').val()==='true',
        community_goals: $('#g_community_goals').val()==='true',
        chat: $('#g_chat').val(),
        bet:{
            strategy: $('#g_strategy').val(),
            percentage: parseInt($('#g_percentage').val()||5),
            percentage_gap: parseInt($('#g_percentage_gap').val()||20),
            max_points: parseInt($('#g_max_points').val()||50000),
            minimum_points: parseInt($('#g_minimum_points').val()||0),
            stealth_mode: $('#g_stealth_mode').val()==='true',
            delay_mode: $('#g_delay_mode').val(),
            delay: parseFloat($('#g_delay').val()||6),
            filter_condition: $('#g_filter_by').val() ? {by: $('#g_filter_by').val(), where: $('#g_filter_where').val()||'GTE', value: parseFloat($('#g_filter_value').val()||0)} : null
        }
    };
    $.ajax({url:'/api/config', method:'PUT', contentType:'application/json', data: JSON.stringify({global}), success:function(res){
        $('#global-save-status').text('Saved ✔').removeClass('err').addClass('ok'); setTimeout(()=>$('#global-save-status').text(''),3000);
    }, error:function(xhr){ $('#global-save-status').text('Error: '+xhr.responseText).addClass('err'); }});
}
function renderPerChannel(streamers){
    const c=$('#per-channel-list'); c.empty();
    if(!streamers || Object.keys(streamers).length===0){ c.html('<p class="empty">No per-channel overrides. Global settings apply to all. Click Add to create per-channel config.</p>'); return; }
    Object.entries(streamers).forEach(([name, cfg])=>{
        const safeName = escapeHtml(name);
        const hasCfg = cfg!==null && cfg!==undefined;
        const bet = hasCfg && cfg.bet ? cfg.bet : {};
        const fc = bet.filter_condition||{};
        const row=$(`
            <div class="channel-row" id="ch-${safeName}">
                <div class="channel-header" onclick="$(this).parent().toggleClass('open')">
                    <span class="name"><i class="fa-solid fa-user"></i> ${safeName} ${hasCfg?'':'<span style="color:var(--muted);font-weight:400">(using global)</span>'}</span>
                    <div class="channel-actions">
                        <button class="btn-small" onclick="event.stopPropagation(); saveChannel(${jsArg(name)})"><i class="fa-solid fa-floppy-disk"></i> Save</button>
                        <button class="btn-small" onclick="event.stopPropagation(); deleteChannel(${jsArg(name)})" title="Delete"><i class="fa-solid fa-trash"></i></button>
                        <i class="fa-solid fa-chevron-down"></i>
                    </div>
                </div>
                <div class="channel-body">
                    <div class="form-grid">
                        <div class="form-group"><label>Make predictions</label><select id="${safeName}_make_predictions"><option value="">Global</option><option value="true">True</option><option value="false">False</option></select></div>
                        <div class="form-group"><label>Follow raid</label><select id="${safeName}_follow_raid"><option value="">Global</option><option value="true">True</option><option value="false">False</option></select></div>
                        <div class="form-group"><label>Claim drops</label><select id="${safeName}_claim_drops"><option value="">Global</option><option value="true">True</option><option value="false">False</option></select></div>
                        <div class="form-group"><label>Chat</label><select id="${safeName}_chat"><option value="">Global</option></select></div>
                        <div class="form-group"><label>Strategy</label><select id="${safeName}_strategy"><option value="">Global</option></select></div>
                        <div class="form-group"><label>Percentage</label><input id="${safeName}_percentage" type="number" placeholder="Global"></div>
                        <div class="form-group"><label>Max points</label><input id="${safeName}_max_points" type="number" placeholder="Global"></div>
                        <div class="form-group"><label>Stealth</label><select id="${safeName}_stealth_mode"><option value="">Global</option><option value="true">True</option><option value="false">False</option></select></div>
                        <div class="form-group"><label>Delay mode</label><select id="${safeName}_delay_mode"><option value="">Global</option></select></div>
                        <div class="form-group"><label>Delay</label><input id="${safeName}_delay" type="number" step="0.1" placeholder="Global"></div>
                        <div class="form-group"><label>Filter by</label><select id="${safeName}_filter_by"><option value="">None/Global</option></select></div>
                        <div class="form-group"><label>Where</label><select id="${safeName}_filter_where"><option value="">-</option></select></div>
                        <div class="form-group"><label>Value</label><input id="${safeName}_filter_value" type="number" step="any" placeholder="Global"></div>
                    </div>
                    <div class="save-status" id="${safeName}-status"></div>
                </div>
            </div>
        `);
        c.append(row);
        if(enumsCache){
            $(`#${safeName}_chat`).append(enumsCache.chat_presences.map(v=>`<option value="${v}">${v}</option>`).join(''));
            $(`#${safeName}_strategy`).append(enumsCache.strategies.map(v=>`<option value="${v}">${v}</option>`).join(''));
            $(`#${safeName}_delay_mode`).append(enumsCache.delay_modes.map(v=>`<option value="${v}">${v}</option>`).join(''));
            $(`#${safeName}_filter_by`).append(enumsCache.outcome_keys.map(v=>`<option value="${v}">${v}</option>`).join(''));
            $(`#${safeName}_filter_where`).append(enumsCache.conditions.map(v=>`<option value="${v}">${v}</option>`).join(''));
        }
        if(hasCfg){
            if(cfg.make_predictions!==undefined && cfg.make_predictions!==null) $(`#${safeName}_make_predictions`).val(String(cfg.make_predictions));
            if(cfg.follow_raid!==undefined && cfg.follow_raid!==null) $(`#${safeName}_follow_raid`).val(String(cfg.follow_raid));
            if(cfg.claim_drops!==undefined && cfg.claim_drops!==null) $(`#${safeName}_claim_drops`).val(String(cfg.claim_drops));
            if(cfg.chat) $(`#${safeName}_chat`).val(cfg.chat);
            if(bet.strategy) $(`#${safeName}_strategy`).val(bet.strategy);
            if(bet.percentage!==undefined) $(`#${safeName}_percentage`).val(bet.percentage);
            if(bet.max_points!==undefined) $(`#${safeName}_max_points`).val(bet.max_points);
            if(bet.stealth_mode!==undefined) $(`#${safeName}_stealth_mode`).val(String(bet.stealth_mode));
            if(bet.delay_mode) $(`#${safeName}_delay_mode`).val(bet.delay_mode);
            if(bet.delay!==undefined) $(`#${safeName}_delay`).val(bet.delay);
            if(fc.by) $(`#${safeName}_filter_by`).val(fc.by);
            if(fc.where) $(`#${safeName}_filter_where`).val(fc.where);
            if(fc.value!==undefined) $(`#${safeName}_filter_value`).val(fc.value);
        }
    });
}
function saveChannel(name){
    const safeName = escapeHtml(name);
    const getVal=(id)=> $(`#${safeName}_${id}`).val();
    const getNum=(id)=> { const v=getVal(id); return v===""||v===null? undefined : parseInt(v, 10); };
    const getFloat=(id)=> { const v=getVal(id); return v===""||v===null? undefined : parseFloat(v); };
    const getBool=(id)=> { const v=getVal(id); return v===""||v===null? undefined : v==='true'; };
    const data={};
    const mp=getBool('make_predictions'); if(mp!==undefined) data.make_predictions=mp;
    const fr=getBool('follow_raid'); if(fr!==undefined) data.follow_raid=fr;
    const cd=getBool('claim_drops'); if(cd!==undefined) data.claim_drops=cd;
    const chat=getVal('chat'); if(chat) data.chat=chat;
    const bet={};
    const strat=getVal('strategy'); if(strat) bet.strategy=strat;
    const perc=getNum('percentage'); if(perc!==undefined) bet.percentage=perc;
    const maxp=getNum('max_points'); if(maxp!==undefined) bet.max_points=maxp;
    const stealth=getBool('stealth_mode'); if(stealth!==undefined) bet.stealth_mode=stealth;
    const dmode=getVal('delay_mode'); if(dmode) bet.delay_mode=dmode;
    const del=getFloat('delay'); if(del!==undefined) bet.delay=del;
    const fby=getVal('filter_by'); const fwh=getVal('filter_where'); const fval=getVal('filter_value');
    if(fby) bet.filter_condition={by:fby, where:fwh||'GTE', value: parseFloat(fval||0)};
    if(Object.keys(bet).length>0) data.bet=bet;
    $.ajax({url:`/api/config/streamer/${encodeURIComponent(name)}`, method:'PUT', contentType:'application/json', data: JSON.stringify(data), success:function(){
        $(`#ch-${safeName} .name span`).remove();
        $(`#${safeName}-status`).text('Saved ✔').removeClass('err').addClass('ok'); setTimeout(()=>$(`#${safeName}-status`).text(''),2000);
    }, error:function(xhr){ $(`#${safeName}-status`).text('Error '+xhr.responseText).addClass('err'); }});
}
function deleteChannel(name){
    const isDockerMode = typeof canAddStreamer !== 'undefined' && !canAddStreamer;
    const promptMsg = isDockerMode
        ? `Reset per-channel config for ${name} to global settings?`
        : `Remove streamer ${name} from miner?`;
    if(!confirm(promptMsg)) return;
    $.ajax({
        url:`/api/config/streamer/${encodeURIComponent(name)}`,
        method:'DELETE',
        success:function(){
            loadConfig(true);
            loadOverview();
            getStreamers();
        },
        error:function(xhr){
            alert('Error: ' + (xhr.responseJSON?.error || xhr.responseText));
        }
    });
}
function addStreamer(){
    if($('#btn-add-streamer').prop('disabled')) return;
    const name=$('#new-streamer-name').val().trim().toLowerCase();
    if(!name) return alert('Enter username');
    const btn = $('#btn-add-streamer');
    btn.prop('disabled', true);
    $.ajax({
        url:'/api/config/streamer',
        method:'POST',
        contentType:'application/json',
        data: JSON.stringify({username:name, settings:null}),
        success:function(){
            btn.prop('disabled', false);
            $('#new-streamer-name').val('');
            loadConfig(true);
            loadOverview();
            getStreamers();
        },
        error:function(xhr){
            btn.prop('disabled', false);
            alert('Error: ' + (xhr.responseJSON?.error || xhr.responseText));
        }
    });
}
function renderPriority(priority){
    const c=$('#priority-editor'); c.empty();
    const list = priority && priority.length>0 ? priority : (enumsCache? enumsCache.priorities.slice(0,3): ['STREAK','DROPS','ORDER']);
    c.html(list.map((p,i)=>{
        const safeP = escapeHtml(p);
        return `<div class="priority-item" draggable="true" data-p="${safeP}" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;margin-bottom:4px;background:var(--bg);cursor:move"><i class="fa-solid fa-grip"></i> ${i+1}. ${safeP} <button class="btn-small" style="float:right" onclick="removePriority(${jsArg(p)})"><i class="fa-solid fa-xmark"></i></button></div>`;
    }).join('') + `<div style="margin-top:8px"><select id="new-priority-val" class="input"></select> <button class="btn-small" onclick="addPriority()"><i class="fa-solid fa-plus"></i> Add</button></div>`);
    if(enumsCache) $('#new-priority-val').html(enumsCache.priorities.map(v=>`<option value="${v}">${v}</option>`).join(''));
    let dragSrc=null;
    $('.priority-item').on('dragstart', function(e){ dragSrc=this; e.originalEvent.dataTransfer.effectAllowed='move'; });
    $('.priority-item').on('dragover', function(e){ e.preventDefault(); });
    $('.priority-item').on('drop', function(e){
        e.preventDefault();
        if(dragSrc && dragSrc!==this){
            const src=$(dragSrc).data('p'), tgt=$(this).data('p');
            const arr=$('#priority-editor .priority-item').map(function(){return $(this).data('p');}).get();
            const sIdx=arr.indexOf(src), tIdx=arr.indexOf(tgt);
            arr.splice(sIdx,1); arr.splice(tIdx,0,src);
            renderPriority(arr);
        }
    });
}
function addPriority(){ const v=$('#new-priority-val').val(); if(!v) return; const arr=$('#priority-editor .priority-item').map(function(){return $(this).data('p');}).get(); if(arr.includes(v)) return; arr.push(v); renderPriority(arr); }
function removePriority(p){ const arr=$('#priority-editor .priority-item').map(function(){return $(this).data('p');}).get().filter(x=>x!==p); renderPriority(arr); }
function savePriority(){ const arr=$('#priority-editor .priority-item').map(function(){return $(this).data('p');}).get(); $.ajax({url:'/api/config', method:'PUT', contentType:'application/json', data: JSON.stringify({priority:arr}), success:function(){ alert('Priority saved'); }}); }

$('.dropdown').click(()=> $('.dropdown').toggleClass('is-active'));

window.changeSortBy=changeSortBy; window.handleStreamerClick=handleStreamerClick; window.goHistoryPage=goHistoryPage; window.saveChannel=saveChannel; window.deleteChannel=deleteChannel; window.removePriority=removePriority; window.addPriority=addPriority;
