(() => {
    const list = document.getElementById('chat-message-list');
    if (!list) return;
    const count = document.getElementById('chat-message-count');
    const liveState = document.getElementById('chat-live-state');
    const empty = document.getElementById('chat-empty');
    const seen = new Set();
    const messageNodes = new Map();
    const defaults = {theme:'transparent',fontSize:16,fontFamily:'Arial, sans-serif',backgroundColor:'#111820',backgroundOpacity:78,textColor:'#f3f5f7',usernameColor:'#ffffff',twitchColor:'#9146ff',youtubeColor:'#e62117',showPlatform:true,showTimestamp:true,showUsername:true,showBadges:true,maxMessages:30,messageSpacing:7,messageRadius:8};
    let appearance = {...defaults};
    let activeView = 'all';
    let sendTarget = 'all';
    let total = 0;
    const pinned = loadPinned();
    const commonBots = {nightbot:/^nightbot$/i,streamelements:/^streamelements?$/i,streamerbot:/^streamer[. _-]?bot$/i,moobot:/^moobot$/i,fossabot:/^fossabot$/i,wizebot:/^wizebot$/i,botrix:/^botrix$/i,sery_bot:/^sery_bot$/i};
    function selectedBotFilters() { try { const value = JSON.parse(localStorage.getItem('llamaqueue-bot-filters') || '[]'); return Array.isArray(value) ? value : []; } catch (_) { return []; } }
    function isFilteredBot(username) { const name = String(username || '').trim(); return selectedBotFilters().some(key => commonBots[key]?.test(name)); }
    const creatorName = (document.getElementById('llama-chat-page')?.dataset.creatorName || '').trim();
    const mentionPattern = creatorName ? new RegExp('(^|\\s)@?' + creatorName.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&') + '(?=$|[\\s.,!?])', 'i') : null;
    const focusButton = document.getElementById('chat-focus-toggle');
    async function enterChatFocus() {
        document.body.classList.add('chat-focus-mode');
        if (focusButton) { focusButton.textContent = 'Exit focus'; focusButton.setAttribute('aria-pressed','true'); }
        try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); } catch (_) { /* CSS focus mode remains available if fullscreen is blocked. */ }
    }
    async function exitChatFocus() {
        document.body.classList.remove('chat-focus-mode');
        if (focusButton) { focusButton.textContent = 'Focus chat'; focusButton.setAttribute('aria-pressed','false'); }
        try { if (document.fullscreenElement) await document.exitFullscreen(); } catch (_) {}
    }
    focusButton?.addEventListener('click', () => document.body.classList.contains('chat-focus-mode') ? exitChatFocus() : enterChatFocus());
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement && document.body.classList.contains('chat-focus-mode')) {
            document.body.classList.remove('chat-focus-mode');
            if (focusButton) { focusButton.textContent = 'Focus chat'; focusButton.setAttribute('aria-pressed','false'); }
        }
    });
    window.addEventListener('keydown', event => { if (event.key === 'Escape' && document.body.classList.contains('chat-focus-mode') && !document.fullscreenElement) exitChatFocus(); });

    function applyAppearance(settings) {
        appearance = {...defaults, ...settings};
        const root = document.documentElement;
        root.style.setProperty('--chat-font', appearance.fontFamily);
        root.style.setProperty('--chat-font-size', `${appearance.fontSize}px`);
        root.style.setProperty('--chat-text', appearance.textColor);
        root.style.setProperty('--chat-username', appearance.usernameColor);
        root.style.setProperty('--chat-twitch', appearance.twitchColor);
        root.style.setProperty('--chat-youtube', appearance.youtubeColor);
        root.style.setProperty('--chat-spacing', `${appearance.messageSpacing}px`);
        root.style.setProperty('--chat-radius', `${appearance.messageRadius}px`);
        const alpha = Math.round(appearance.backgroundOpacity * 2.55).toString(16).padStart(2,'0');
        root.style.setProperty('--chat-bubble', appearance.theme === 'transparent' ? `${appearance.backgroundColor}${alpha}` : appearance.theme === 'light' ? 'rgba(255,255,255,.88)' : 'rgba(10,14,20,.94)');
        document.body.classList.toggle('chat-theme-light', appearance.theme === 'light');
        document.body.classList.toggle('chat-theme-dark', appearance.theme === 'dark');
        document.body.classList.toggle('chat-hide-platform', !appearance.showPlatform);
        document.body.classList.toggle('chat-hide-time', !appearance.showTimestamp);
        document.body.classList.toggle('chat-hide-user', !appearance.showUsername);
    }

    function bindAppearanceControls() {
        const config = document.getElementById('chat-appearance-json');
        try { if (config) applyAppearance(JSON.parse(config.textContent)); } catch (_) { applyAppearance(defaults); }
        document.querySelectorAll('[data-setting]').forEach(control => {
            const key = control.dataset.setting;
            if (control.type === 'checkbox') control.checked = !!appearance[key]; else control.value = appearance[key];
            const output = document.querySelector(`[data-output="${key}"]`);
            if (output) output.textContent = control.value;
            control.addEventListener('input', () => {
                appearance[key] = control.type === 'checkbox' ? control.checked : (control.type === 'range' ? Number(control.value) : control.value);
                if (output) output.textContent = control.value;
                applyAppearance(appearance);
            });
        });
        document.getElementById('save-chat-appearance')?.addEventListener('click', async () => {
            const status = document.getElementById('appearance-save-status');
            try {
                const response = await fetch('/chat/api/appearance', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(appearance)});
                if (!response.ok) throw new Error(`Save failed (${response.status})`);
                appearance = await response.json();
                if (status) status.textContent = 'Saved. OBS overlay uses these settings too.';
            } catch (error) { if (status) status.textContent = error.message; }
        });
        document.getElementById('reset-chat-appearance')?.addEventListener('click', () => {
            applyAppearance(defaults);
            document.querySelectorAll('[data-setting]').forEach(control => {
                const key = control.dataset.setting;
                if (control.type === 'checkbox') control.checked = defaults[key]; else control.value = defaults[key];
                const output = document.querySelector(`[data-output="${key}"]`); if (output) output.textContent = control.value;
            });
            const status = document.getElementById('appearance-save-status'); if (status) status.textContent = 'Defaults loaded. Save to keep them.';
        });
    }

    function loadPinned() {
        try { const value = JSON.parse(localStorage.getItem('llamaqueue-pinned-chatters') || '[]'); return Array.isArray(value) ? value.slice(0, 20) : []; }
        catch (_) { return []; }
    }
    function savePinned() { localStorage.setItem('llamaqueue-pinned-chatters', JSON.stringify(pinned)); }
    function refreshPinButtons() {
        list.querySelectorAll('.chat-message').forEach(row => {
            const button = row.querySelector('.chat-pin-chatter');
            if (!button) return;
            const isPinned = pinned.some(person => person.key === row.dataset.userKey);
            button.textContent = isPinned ? 'Unpin' : 'Pin chatter';
            button.setAttribute('aria-pressed', String(isPinned));
        });
    }
    function chatterKey(platform, userId, username) { return `${platform}:${userId || String(username || 'viewer').toLowerCase()}`; }

    function renderPinnedTabs() {
        const host = document.getElementById('pinned-chatter-tabs');
        if (!host) return;
        host.replaceChildren();
        if (!pinned.length) {
            const hint = document.createElement('span'); hint.className = 'chat-pinned-empty'; hint.textContent = 'Pin a chatter from any message'; host.append(hint); return;
        }
        pinned.forEach(person => {
            const button = document.createElement('button');
            button.type = 'button'; button.className = `chat-tab pinned-tab ${activeView === `pinned:${person.key}` ? 'active' : ''}`;
            button.dataset.pinned = person.key;
            const platform = document.createElement('span'); platform.className = `tab-dot ${person.platform}-dot`;
            const name = document.createElement('span'); name.textContent = person.username;
            if (person.mentioned) button.classList.add('has-mention');
            const remove = document.createElement('span'); remove.className = 'unpin-x'; remove.textContent = '×'; remove.title = 'Unpin chatter';
            button.append(platform, name, remove);
            button.addEventListener('click', event => {
                if (event.target === remove) {
                    const index = pinned.findIndex(item => item.key === person.key); if (index >= 0) pinned.splice(index, 1);
                    if (activeView === `pinned:${person.key}`) activeView = 'all';
                    savePinned(); renderPinnedTabs(); refreshPinButtons(); updateVisibility(); return;
                }
                person.mentioned = false; savePinned();
                activeView = `pinned:${person.key}`; renderPinnedTabs(); updateMainTabs(); updateVisibility();
                setSendTarget(person.platform);
            });
            host.append(button);
        });
    }

    function updateMainTabs() {
        document.querySelectorAll('.chat-tab[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === activeView));
    }
    function updateVisibility() {
        list.querySelectorAll('.chat-message').forEach(row => {
            let visible = activeView === 'all' || row.dataset.platform === activeView;
            if (activeView.startsWith('pinned:')) visible = row.dataset.userKey === activeView.slice(7);
            row.hidden = !visible || isFilteredBot(row.dataset.username);
        });
        if (count) count.textContent = `${list.querySelectorAll('.chat-message:not([hidden])').length} visible · ${total} received`;
    }
    function setSendTarget(target) {
        sendTarget = target;
        document.querySelectorAll('.chat-send-target').forEach(button => button.classList.toggle('active', button.dataset.target === target));
    }

    function markDeleted(platform, messageId, deletedBy) {
        const row = messageNodes.get(`${platform}:${messageId}`);
        if (!row) return;
        row.classList.add('chat-message-deleted');
        const text = row.querySelector('.chat-message-text');
        if (text && !row.querySelector('.chat-deleted-label')) {
            const label = document.createElement('span'); label.className = 'chat-deleted-label'; label.textContent = `Message deleted${deletedBy ? ` by ${deletedBy}` : ''}`;
            text.before(label);
        }
        const deleteButton = row.querySelector('.chat-delete-message'); if (deleteButton) deleteButton.remove();
    }

    function addMessage(message) {
        if (!message || !message.text) return;
        const isBot = Object.values(commonBots).some(pattern => pattern.test(String(message.username || '').trim()));
        if (isFilteredBot(message.username)) return;
        const id = String(message.id || `${message.username}:${message.timestamp}:${message.text}`);
        const key = `${message.platform}:${id}`;
        if (seen.has(key)) return;
        seen.add(key);
        if (empty) empty.remove();
        const row = document.createElement('article');
        row.className = 'chat-message'; row.dataset.platform = message.platform;
        row.dataset.userKey = chatterKey(message.platform, message.user_id, message.username);
        row.dataset.isBot = isBot ? '1' : '0';
        row.dataset.username = String(message.username || '');
        row.dataset.messageId = id;
        const badge = document.createElement('span'); badge.className = `chat-message-platform ${message.platform}`; badge.textContent = message.platform === 'twitch' ? 'T' : '▶';
        const content = document.createElement('div'); content.className = 'chat-message-content';
        const meta = document.createElement('div'); meta.className = 'chat-message-meta';
        const username = document.createElement('span'); username.className = 'chat-message-user'; username.textContent = message.username || 'Viewer';
        if (message.moderator || message.owner || message.broadcaster) { const role = document.createElement('span'); role.className = 'chat-role-icon' + (message.owner || message.broadcaster ? ' lead' : ''); role.textContent = message.owner || message.broadcaster ? '★' : '◆'; role.title = message.owner || message.broadcaster ? 'Channel owner / lead' : 'Moderator'; role.setAttribute('aria-label', role.title); username.append(role); }
        const time = document.createElement('span'); time.className = 'chat-message-time';
        const date = new Date(message.timestamp || Date.now()); time.textContent = Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
        const text = document.createElement('div'); text.className = 'chat-message-text'; text.textContent = message.text;
        meta.append(username);
        if (appearance.showBadges) {
            if (message.subscription_badge) {
                const subTag = document.createElement('span');
                subTag.className = 'chat-user-badge chat-subscription-badge';
                subTag.textContent = String(message.subscription_badge).slice(0, 12);
                meta.append(subTag);
            }
            if (message.tenure_badge) {
                const tenureTag = document.createElement('span');
                tenureTag.className = 'chat-user-badge chat-tenure-badge';
                tenureTag.textContent = String(message.tenure_badge).slice(0, 8);
                meta.append(tenureTag);
            }
            (message.badge_icons || []).slice(0, 6).forEach((src, index) => { if (!/^https:\/\//i.test(src)) return; const icon = document.createElement('img'); icon.className='chat-platform-badge-icon'; icon.src=src; icon.alt='Twitch badge'; icon.title='Twitch badge'; icon.loading='lazy'; meta.append(icon); });
            const labels = [...(message.badges || [])].filter(label => !/^moderator$/i.test(String(label)));
            if (message.member && !message.subscription_badge && !labels.includes('Member')) labels.push('Member');
            if (message.verified && !labels.includes('Verified')) labels.push('Verified');

            if (message.vip) labels.push('VIP'); if (message.broadcaster || message.owner) labels.push('Owner');
            labels.slice(0, 6).forEach(label => { const tag = document.createElement('span'); tag.className = 'chat-user-badge'; tag.textContent = String(label).replace(/[^a-z0-9 _-]/gi,'').slice(0,32); meta.append(tag); });
        }
        meta.append(time); content.append(meta, text);
        const actions = document.createElement('div'); actions.className = 'chat-message-actions';
        const pin = document.createElement('button'); pin.type = 'button'; pin.className = 'chat-message-action chat-pin-chatter';
        const person = {key: row.dataset.userKey, platform: message.platform, userId: message.user_id || null, username: message.username || 'Viewer'};
        const isModerator = !!(message.moderator || message.owner || message.broadcaster);
        const mentionsCreator = !!(mentionPattern && mentionPattern.test(String(message.text)));
        if (isModerator && mentionsCreator) {
            row.classList.add('chat-message-mentioned');
            const existing = pinned.find(item => item.key === person.key);
            if (existing) existing.mentioned = true;
            else { if (pinned.length >= 20) pinned.shift(); pinned.push({...person, mentioned:true, autoPinned:true}); }
            savePinned(); renderPinnedTabs();
        }
        const isPinned = () => pinned.some(item => item.key === person.key);
        pin.textContent = isPinned() ? 'Unpin' : 'Pin chatter';
        pin.setAttribute('aria-pressed', String(isPinned()));
        pin.addEventListener('click', () => {
            const index = pinned.findIndex(item => item.key === person.key);
            if (index >= 0) pinned.splice(index, 1); else { if (pinned.length >= 20) pinned.shift(); pinned.push(person); }
            savePinned(); renderPinnedTabs(); refreshPinButtons();
        });
        actions.append(pin);
        if (message.user_id && !String(message.id || '').startsWith('preview-') && !message.broadcaster && !message.owner) {
            const timeout = document.createElement('button'); timeout.type='button'; timeout.className='chat-message-action'; timeout.textContent='Timeout 10m';
            timeout.addEventListener('click', async () => {
                if (!window.confirm(`Timeout ${message.username || 'this chatter'} for 10 minutes on ${message.platform}?`)) return;
                timeout.disabled=true; timeout.textContent='Applying…';
                try {
                    const response=await fetch('/chat/api/moderate/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:message.platform,user_id:message.user_id,action:'timeout'})});
                    const result=await response.json(); if(!response.ok) throw new Error(result.error || 'Timeout failed');
                    timeout.textContent='Timed out'; const status=document.getElementById('chat-send-status'); if(status) status.textContent=`${message.username} timed out on ${message.platform}.`;
                } catch(error) { timeout.disabled=false; timeout.textContent='Timeout 10m'; window.alert(error.message); }
            });
            const ban = document.createElement('button'); ban.type='button'; ban.className='chat-message-action chat-delete-message'; ban.textContent='Ban';
            ban.addEventListener('click', async () => {
                if (!window.confirm(`Permanently ban ${message.username || 'this chatter'} from ${message.platform}?`)) return;
                ban.disabled=true; ban.textContent='Banning…';
                try {
                    const response=await fetch('/chat/api/moderate/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:message.platform,user_id:message.user_id,action:'ban'})});
                    const result=await response.json(); if(!response.ok) throw new Error(result.error || 'Ban failed');
                    ban.textContent='Banned'; const status=document.getElementById('chat-send-status'); if(status) status.textContent=`${message.username} banned on ${message.platform}.`;
                } catch(error) { ban.disabled=false; ban.textContent='Ban'; window.alert(error.message); }
            });
            actions.append(timeout, ban);
        }
        if (message.id && !String(message.id).startsWith('preview-')) {
            const del = document.createElement('button'); del.type = 'button'; del.className = 'chat-message-action chat-delete-message'; del.textContent = 'Delete';
            del.addEventListener('click', async () => {
                del.disabled = true; del.textContent = 'Deleting…';
                try {
                    const response = await fetch('/chat/api/moderate/delete', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:message.platform,message_id:message.id})});
                    const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Delete failed');
                    markDeleted(message.platform, id, 'You');
                    const status=document.getElementById('chat-send-status'); if(status) status.textContent=`Message deleted on ${message.platform}.`;
                } catch (error) { del.disabled = false; del.textContent = 'Delete'; const status=document.getElementById('chat-send-status'); if(status) status.textContent=`Delete failed on ${message.platform}: ${error.message}`; window.alert(error.message); }
            });
            actions.append(del);
        }
        content.append(actions); row.append(badge, content); list.append(row); messageNodes.set(key, row);
        if (message.deleted) markDeleted(message.platform, id, message.deleted_by);
        while (list.querySelectorAll('.chat-message').length > appearance.maxMessages) {
            const oldest = list.querySelector('.chat-message');
            if (oldest) { messageNodes.delete(`${oldest.dataset.platform}:${oldest.dataset.messageId}`); oldest.remove(); }
        }
        total += 1; updateVisibility();
        if (activeView === 'all' || row.dataset.platform === activeView || activeView === `pinned:${row.dataset.userKey}`) list.scrollTop = list.scrollHeight;
    }

    renderPinnedTabs(); bindAppearanceControls();
    document.querySelectorAll('.chat-tab[data-view]').forEach(button => button.addEventListener('click', () => {
        activeView = button.dataset.view; updateMainTabs(); renderPinnedTabs(); updateVisibility();
        setSendTarget(activeView === 'all' ? 'all' : activeView);
    }));
    document.querySelectorAll('.chat-send-target').forEach(button => button.addEventListener('click', () => setSendTarget(button.dataset.target)));

    document.getElementById('chat-composer')?.addEventListener('submit', async event => {
        event.preventDefault();
        const input = document.getElementById('chat-message-input'); const status = document.getElementById('chat-send-status'); const button = document.getElementById('chat-send-button');
        const message = input.value.trim(); if (!message) return;
        button.disabled = true; status.textContent = `Sending to ${sendTarget === 'all' ? 'Twitch and YouTube' : sendTarget}…`;
        try {
            const response = await fetch('/chat/api/send', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,target:sendTarget})});
            const result = await response.json();
            const failed = Object.entries(result.results || {}).filter(([, value]) => !value.ok);
            const sent = Object.entries(result.results || {}).filter(([, value]) => value.ok).map(([platform]) => platform);
            if (!response.ok) throw new Error(failed.map(([platform,value]) => `${platform}: ${value.error}`).join(' · ') || result.error || 'Message was not sent');
            input.value = ''; status.textContent = `Sent to ${sent.join(' and ')}${failed.length ? ` · Failed: ${failed.map(([p,v]) => `${p}: ${v.error}`).join(' · ')}` : ''}`;
        } catch (error) { status.textContent = error.message; }
        finally { button.disabled = false; input.focus(); }
    });

    document.getElementById('preview-chat')?.addEventListener('click', () => {
        const run = Date.now();
        [
            {id:`preview-t1-${run}`,platform:'twitch',user_id:'preview-t1',username:'TrailBoss42',text:'Howdy folks! Chat is looking mighty fine.',timestamp:new Date().toISOString(),subscription_badge:'T1',tenure_badge:'1Y',badges:[],moderator:false},
            {id:`preview-y1-${run}`,platform:'youtube',user_id:'preview-y1',username:'Llama Wrangler',text:'Testing the unified chat overlay. Can you see this?',timestamp:new Date().toISOString(),verified:true,member:true,subscription_badge:'MEM',tenure_badge:'6M',badges:['Verified']},
            {id:`preview-t2-${run}`,platform:'twitch',user_id:'preview-t2',username:'PixelPioneer',text:'The colors and spacing are looking good!',timestamp:new Date().toISOString(),subscription_badge:'T3',tenure_badge:'2Y',moderator:true,badges:['moderator']},
            {id:`preview-y2-${run}`,platform:'youtube',user_id:'preview-y2',username:'CraftyViewer',text:'Transparent background is ready for OBS.',timestamp:new Date().toISOString()}
        ].forEach(addMessage);
        if (count) count.textContent = 'Sample preview · not live messages';
    });

    function setStatus(platform, status) {
        const label = document.getElementById(`${platform}-status`); const dot = document.getElementById(`${platform}-status-dot`);
        if (label) label.textContent = status;
        if (dot) { dot.classList.toggle('connected',status.toLowerCase().includes('connected') && !status.toLowerCase().includes('error')); dot.classList.toggle('error',status.toLowerCase().includes('error') || status.toLowerCase().includes('failed')); }
    }

    const copyButton = document.getElementById('copy-overlay-url');
    copyButton?.addEventListener('click', async () => {
        const input = document.getElementById('chat-overlay-url');
        try { await navigator.clipboard.writeText(input.value); copyButton.textContent = 'Copied!'; }
        catch (_) { input.select(); document.execCommand('copy'); copyButton.textContent = 'Copied!'; }
        setTimeout(() => copyButton.textContent = 'Copy URL', 1600);
    });

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${location.host}/chat/ws`);
    socket.addEventListener('open', () => { if (liveState) liveState.textContent = 'Chat connection active'; socket.send('ready'); });
    socket.addEventListener('message', event => {
        const data = JSON.parse(event.data);
        if (data.type === 'snapshot') { (data.messages || []).forEach(addMessage); Object.entries(data.status || {}).forEach(([platform,status]) => setStatus(platform,status)); }
        else if (data.type === 'message') addMessage(data.message);
        else if (data.type === 'message_deleted') markDeleted(data.platform, data.message_id, data.deleted_by);
        else if (data.type === 'status') setStatus(data.platform, data.status);
    });
    socket.addEventListener('close', () => { if (liveState) liveState.textContent = 'Chat disconnected · refresh to reconnect'; });
    socket.addEventListener('error', () => { if (liveState) liveState.textContent = 'Chat connection error'; });
    const heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send('ping'); }, 20000);
    window.addEventListener('beforeunload', () => { clearInterval(heartbeat); socket.close(); });
})();
