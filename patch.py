import re

def patch_index():
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add .card-thumb CSS
    thumb_css = """
    /* ── CARD THUMB ── */
    .card-thumb {
      height: 140px;
      background-size: cover;
      background-position: center;
      background-color: var(--surface-2);
      border-bottom: 2px solid var(--rim);
    }
    
    /* ── CARD BODY ── */
"""
    content = content.replace("    /* ── CARD BODY ── */", thumb_css)
    
    # Increase padding of card-body to make tiles bigger
    content = content.replace("padding: 13px 13px 11px 17px;", "padding: 18px 18px 16px 22px;")

    # 2. Update renderCard HTML
    old_return = """    return `
      <article class="card ${cc} ${picked ? 'picked-card' : ''} ${ribbonClass}" data-id="${escHtml(job.id)}" data-url="${escHtml(url)}" style="animation-delay:${delay}ms" ${ribbonAttr}>
        ${isNew ? '<div class="new-dot" title="New batch"></div>' : ''}
        <div class="card-body">
          <div class="card-top-row">
            <div class="card-title-block">
              <span class="cat-tag ${cc}">${escHtml(job.category)}</span>
              <div class="job-title">
                <a href="${escHtml(url)}" target="_blank" rel="noreferrer" data-action="open-link">${escHtml(job.title || 'Untitled')}</a>
              </div>
              <div class="company-name">${escHtml(job.company || 'Unknown company')}</div>
            </div>
            <button class="heart-btn ${picked ? 'picked' : ''}" data-action="pick" aria-label="Pick job">${picked ? '&#9829;' : '&#9825;'}</button>
          </div>

          <div class="stars-row">
            <div class="stars" aria-label="${rating} of 5 stars">
              ${[1,2,3,4,5].map(v => `<button class="star-btn ${v <= rating ? 'on' : ''}" data-action="rate" data-rating="${v}" title="${v} star">${v <= rating ? '&#9733;' : '&#9734;'}</button>`).join('')}
            </div>
            <span class="rating-txt">${rating ? `${rating}/5` : 'Rate'}</span>
          </div>

          <div class="meta-list">
            <span class="meta-pill source">${escHtml(job.source)}</span>
            <span class="meta-pill date">${formatDateShort(job.seen_at)}</span>
            </button>
            <button class="action-btn copy-id-btn" data-action="copy-id" title="Copy Job ID: ${escHtml(job.id)}" style="flex:0;padding:0 10px">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
          </div>

          ${compatData ? `
          <div class="compat-bar">
            <div class="compat-track">
              <div class="compat-fill" style="width:${compatData.pct}%;background:${compatData.pct>=70?'var(--teal)':compatData.pct>=40?'var(--amber)':'var(--rose)'}"></div>
            </div>
            <span class="compat-label" style="color:${compatData.pct>=70?'var(--teal)':compatData.pct>=40?'var(--amber)':'var(--rose)'}">${compatData.pct}% match</span>
          </div>` : ''}
        </div>
      </article>
    `;"""

    new_return = """    const imgHtml = job.image_url ? `<div class="card-thumb" style="background-image:url('${escHtml(job.image_url)}')"></div>` : '';
    
    return `
      <article class="card ${cc} ${picked ? 'picked-card' : ''} ${ribbonClass}" data-id="${escHtml(job.id)}" data-url="${escHtml(url)}" style="animation-delay:${delay}ms" ${ribbonAttr}>
        ${isNew ? '<div class="new-dot" title="New batch"></div>' : ''}
        ${imgHtml}
        <div class="card-body">
          <div class="card-top-row">
            <div class="card-title-block">
              <span class="cat-tag ${cc}">${escHtml(job.category)}</span>
              <div class="job-title">
                <a href="${escHtml(url)}" target="_blank" rel="noreferrer" data-action="open-link">${escHtml(job.title || 'Untitled')}</a>
              </div>
              <div class="company-name">${escHtml(job.company || 'Unknown company')}</div>
            </div>
            <button class="heart-btn ${picked ? 'picked' : ''}" data-action="pick" aria-label="Pick job">${picked ? '&#9829;' : '&#9825;'}</button>
          </div>

          <div class="stars-row">
            <div class="stars" aria-label="${rating} of 5 stars">
              ${[1,2,3,4,5].map(v => `<button class="star-btn ${v <= rating ? 'on' : ''}" data-action="rate" data-rating="${v}" title="${v} star">${v <= rating ? '&#9733;' : '&#9734;'}</button>`).join('')}
            </div>
            <span class="rating-txt">${rating ? `${rating}/5` : 'Rate'}</span>
          </div>

          <div class="meta-list">
            <span class="meta-pill source">${escHtml(job.source)}</span>
            <span class="meta-pill date">${formatDateShort(job.seen_at)}</span>
            <button class="action-btn copy-id-btn" data-action="copy-id" title="Copy Job ID: ${escHtml(job.id)}" style="flex:0;padding:0 10px;height:20px;">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
          </div>

          ${compatData ? `
          <div class="compat-bar">
            <div class="compat-track">
              <div class="compat-fill" style="width:${compatData.pct}%;background:${compatData.pct>=70?'var(--teal)':compatData.pct>=40?'var(--amber)':'var(--rose)'}"></div>
            </div>
            <span class="compat-label" style="color:${compatData.pct>=70?'var(--teal)':compatData.pct>=40?'var(--amber)':'var(--rose)'}">${compatData.pct}% match</span>
          </div>` : ''}

          <div class="action-row" style="margin-top: 10px;">
            <button class="action-btn prompt-btn" data-action="copy-prompt">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="margin-right:2px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              Prompt
            </button>
            <button class="action-btn import-btn ${compatData ? 'mapped' : ''}" data-action="import">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="margin-right:2px"><polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line></svg>
              Import
            </button>
            <button class="action-btn archive-btn" data-action="archive">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="margin-right:2px"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
              Archive
            </button>
          </div>
        </div>

        <div class="card-footer">
          <a class="open-btn" href="${escHtml(url)}" target="_blank" data-action="open-link">View Job</a>
          <button class="pick-btn ${picked ? 'active' : ''}" data-action="pick">${picked ? 'Picked' : 'Pick'}</button>
        </div>
      </article>
    `;"""

    content = content.replace(old_return, new_return)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)

patch_index()
