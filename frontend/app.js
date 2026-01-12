// ==============================
// CONFIGURATION
// ==============================
const CONFIG = {
    API_BASE_URL: "http://localhost:8080",
    DEFAULT_USER_ID: "anonymous",
    ITEMS_PER_PAGE: 12,
    MAX_FILE_SIZE: 10 * 1024 * 1024 // 10MB
};

// ==============================
// STATE MANAGEMENT
// ==============================
const STATE = {
    wardrobeItems: [],
    currentOutfits: [],
    currentCategory: "all",
    isLoading: false,
    currentPage: 1,
    hasMoreItems: true
};

// ==============================
// ELEMENTS
// ==============================
const elements = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileinput"),
    chooseBtn: document.getElementById("chooseBtn"),
    preview: document.getElementById("preview"),
    previewEmpty: document.getElementById("preview-empty"),
    wardrobe: document.getElementById("wardrobe"),
    wardrobeEmpty: document.getElementById("wardrobe-empty"),
    generateForm: document.getElementById("generate-form"),
    outfitsGrid: document.getElementById("outfits-grid"),
    resultsPlaceholder: document.getElementById("results-placeholder"),
    totalItems: document.getElementById("total-items"),
    categoriesCount: document.getElementById("categories-count"),
    categoryFilter: document.getElementById("category-filter"),
    focusItemSelect: document.getElementById("focus-item"),
    numOutfitsSlider: document.getElementById("num-outfits"),
    numOutfitsValue: document.getElementById("num-outfits-value"),
    refreshWardrobeBtn: document.getElementById("refresh-wardrobe"),
    loadingModal: document.getElementById("loading-modal"),
    weatherPreview: document.getElementById("weather-preview"),
    weatherDisplay: document.getElementById("weather-display"),
    occasionSelect: document.getElementById("occasion"),
    cityInput: document.getElementById("city"),
    saveAllOutfitsBtn: document.getElementById("save-all-outfits"),
    wardrobeStats: document.getElementById("wardrobe-stats")
};

// ==============================
// INITIALIZATION
// ==============================
document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 SmartStylist Frontend Initializing...");
    initializeApp();
});

async function initializeApp() {
    try {
        // Setup all event listeners
        setupEventListeners();
        
        // Check API health
        await checkAPIHealth();
        
        // Load initial data
        await loadWardrobeItems();
        
        // Setup number of outfits slider
        if (elements.numOutfitsSlider && elements.numOutfitsValue) {
            elements.numOutfitsSlider.addEventListener('input', (e) => {
                elements.numOutfitsValue.textContent = e.target.value;
            });
        }
        
        console.log("✅ SmartStylist Frontend Ready!");
        
        // Show welcome notification
        setTimeout(() => {
            showNotification("Welcome to SmartStylist! Upload clothing items to get started.", "info");
        }, 1000);
        
    } catch (error) {
        console.error("❌ Initialization failed:", error);
        showNotification("Failed to initialize app. Please check console for errors.", "error");
    }
}

// ==============================
// EVENT LISTENERS
// ==============================
function setupEventListeners() {
    // File upload
    if (elements.chooseBtn) {
        elements.chooseBtn.addEventListener("click", () => {
            if (elements.fileInput) elements.fileInput.click();
        });
    }
    
    if (elements.fileInput) {
        elements.fileInput.addEventListener("change", handleFileSelection);
    }
    
    // Drag & drop
    if (elements.dropzone) {
        ["dragenter", "dragover"].forEach(event => {
            elements.dropzone.addEventListener(event, (e) => {
                e.preventDefault();
                elements.dropzone.classList.add("active");
            });
        });
        
        ["dragleave", "drop"].forEach(event => {
            elements.dropzone.addEventListener(event, (e) => {
                e.preventDefault();
                elements.dropzone.classList.remove("active");
            });
        });
        
        elements.dropzone.addEventListener("drop", handleDrop);
    }
    
    // Form submission
    if (elements.generateForm) {
        elements.generateForm.addEventListener("submit", handleGenerateOutfits);
    }
    
    // Category filter
    if (elements.categoryFilter) {
        elements.categoryFilter.addEventListener("click", handleCategoryFilterClick);
    }
    
    // Refresh wardrobe
    if (elements.refreshWardrobeBtn) {
        elements.refreshWardrobeBtn.addEventListener("click", () => loadWardrobeItems());
    }
    
    // City input for weather preview
    if (elements.cityInput) {
        elements.cityInput.addEventListener("blur", () => {
            const city = elements.cityInput.value.trim();
            if (city) {
                updateWeatherPreview(city);
            }
        });
    }
    
    // Save all outfits
    if (elements.saveAllOutfitsBtn) {
        elements.saveAllOutfitsBtn.addEventListener("click", saveAllOutfits);
    }
}

// ==============================
// API HEALTH CHECK
// ==============================
async function checkAPIHealth() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/health`);
        if (!response.ok) {
            showNotification("Backend API is not responding", "warning");
            return false;
        }
        
        const data = await response.json();
        console.log("✅ API Health:", data);
        return true;
        
    } catch (error) {
        console.error("❌ API Health Check Failed:", error);
        showNotification("Cannot connect to backend server. Make sure Flask is running on port 8080.", "error");
        return false;
    }
}

// ==============================
// FILE HANDLING
// ==============================
function handleDrop(e) {
    const files = e.dataTransfer.files;
    handleFiles(files);
}

function handleFileSelection(e) {
    const files = e.target.files;
    handleFiles(files);
}

function handleFiles(fileList) {
    const files = Array.from(fileList);
    if (files.length === 0) return;
    
    let validFiles = 0;
    
    files.forEach(file => {
        // Validate file
        if (!file.type.startsWith("image/")) {
            showNotification(`${file.name} is not an image file`, "warning");
            return;
        }
        
        if (file.size > CONFIG.MAX_FILE_SIZE) {
            showNotification(`${file.name} is too large (max 10MB)`, "warning");
            return;
        }
        
        validFiles++;
        
        // Show preview immediately
        showPreview(file);
        
        // Upload to backend
        uploadImage(file);
    });
    
    if (validFiles > 0) {
        showNotification(`Uploading ${validFiles} image${validFiles > 1 ? 's' : ''}...`, "info");
    }
}

function showPreview(file) {
    const reader = new FileReader();
    
    reader.onload = () => {
        const previewItem = document.createElement("div");
        previewItem.className = "preview-item animate-slide-in";
        previewItem.innerHTML = `
            <div class="preview-image-container">
                <img src="${reader.result}" alt="${file.name}" class="preview-image" />
                <div class="preview-overlay">
                    <div class="preview-loading">
                        <i class="fas fa-spinner fa-spin"></i>
                        <span>Analyzing...</span>
                    </div>
                </div>
            </div>
            <div class="preview-info">
                <div class="preview-filename">${truncateText(file.name, 20)}</div>
                <div class="preview-size">${formatFileSize(file.size)}</div>
            </div>
        `;
        
        // Hide empty state
        if (elements.previewEmpty) {
            elements.previewEmpty.style.display = "none";
        }
        
        // Add to preview section
        if (elements.preview) {
            elements.preview.prepend(previewItem);
        }
    };
    
    reader.readAsDataURL(file);
}

async function uploadImage(file) {
    const formData = new FormData();
    formData.append("image", file);
    formData.append("description", file.name.substring(0, 50));
    formData.append("user_id", CONFIG.DEFAULT_USER_ID);

    showLoading("Analyzing Image", "AI is analyzing your clothing item...");

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/analyze`, {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        
        if (data.status === "success") {
            updatePreviewWithAnalysis(file.name, data.analysis, data.item);
            showNotification(`✅ ${data.analysis.category || 'Clothing'} uploaded successfully!`, "success");
            
            // Reload wardrobe after a short delay
            setTimeout(() => loadWardrobeItems(), 1000);
        } else {
            showNotification(`Upload failed: ${data.error || "Unknown error"}`, "error");
            // Remove the failed preview item
            removeFailedPreview(file.name);
        }
        
    } catch (error) {
        console.error("Upload failed:", error);
        showNotification("Upload failed: " + error.message, "error");
        removeFailedPreview(file.name);
    } finally {
        hideLoading();
    }
}

function updatePreviewWithAnalysis(filename, analysis, item) {
    const previewItems = document.querySelectorAll(".preview-item");
    
    previewItems.forEach(previewItem => {
        const img = previewItem.querySelector("img");
        if (img && img.alt === filename) {
            const overlay = previewItem.querySelector(".preview-overlay");
            if (overlay) {
                overlay.innerHTML = `
                    <div class="preview-analysis">
                        <div class="analysis-category">${analysis.category || 'Clothing'}</div>
                        <div class="analysis-color">${analysis.color || 'Unknown'}</div>
                        ${analysis.style_tags && analysis.style_tags.length > 0 
                            ? `<div class="analysis-tags">${analysis.style_tags.slice(0, 2).join(', ')}</div>`
                            : ''
                        }
                    </div>
                `;
                overlay.classList.remove("preview-loading");
                overlay.classList.add("preview-analysis");
            }
            
            // Add success animation
            previewItem.classList.add("preview-success");
            
            // Remove after 5 seconds
            setTimeout(() => {
                previewItem.classList.add("preview-fade-out");
                setTimeout(() => {
                    if (previewItem.parentNode) {
                        previewItem.parentNode.removeChild(previewItem);
                    }
                    
                    // Show empty state if no more previews
                    if (elements.preview && elements.preview.children.length === 0 && elements.previewEmpty) {
                        elements.previewEmpty.style.display = "flex";
                    }
                }, 300);
            }, 5000);
        }
    });
}

function removeFailedPreview(filename) {
    const previewItems = document.querySelectorAll(".preview-item");
    
    previewItems.forEach(previewItem => {
        const img = previewItem.querySelector("img");
        if (img && img.alt === filename) {
            previewItem.classList.add("preview-error");
            setTimeout(() => {
                if (previewItem.parentNode) {
                    previewItem.parentNode.removeChild(previewItem);
                }
                
                // Show empty state if no more previews
                if (elements.preview && elements.preview.children.length === 0 && elements.previewEmpty) {
                    elements.previewEmpty.style.display = "flex";
                }
            }, 1000);
        }
    });
}

// ==============================
// WARDROBE MANAGEMENT
// ==============================
async function loadWardrobeItems() {
    if (STATE.isLoading) return;
    
    STATE.isLoading = true;
    if (elements.refreshWardrobeBtn) {
        elements.refreshWardrobeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
        elements.refreshWardrobeBtn.disabled = true;
    }
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/wardrobe?user_id=${CONFIG.DEFAULT_USER_ID}`);
        const data = await response.json();
        
        if (data.status === "success") {
            STATE.wardrobeItems = data.items;
            STATE.hasMoreItems = data.pagination?.has_more || false;
            
            updateWardrobeDisplay(data.items);
            updateWardrobeStats(data);
            populateFocusItems(data.items);
            updateCategoryFilter(data.items);
            
            console.log(`✅ Loaded ${data.items.length} wardrobe items`);
        } else {
            showNotification("Failed to load wardrobe items: " + (data.error || "Unknown error"), "error");
        }
    } catch (error) {
        console.error("Failed to load wardrobe:", error);
        showNotification("Failed to load wardrobe items", "error");
    } finally {
        STATE.isLoading = false;
        if (elements.refreshWardrobeBtn) {
            elements.refreshWardrobeBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            elements.refreshWardrobeBtn.disabled = false;
        }
    }
}

function updateWardrobeDisplay(items) {
    const wardrobeGrid = document.querySelector(".wardrobe-grid");
    if (!wardrobeGrid) return;
    
    if (!items || items.length === 0) {
        if (elements.wardrobeEmpty) {
            elements.wardrobeEmpty.style.display = "block";
        }
        wardrobeGrid.innerHTML = "";
        return;
    }
    
    if (elements.wardrobeEmpty) {
        elements.wardrobeEmpty.style.display = "none";
    }
    
    // Clear and add all items
    wardrobeGrid.innerHTML = "";
    
    items.forEach(item => {
        const itemCard = createWardrobeItemCard(item);
        wardrobeGrid.appendChild(itemCard);
    });
}

function createWardrobeItemCard(item) {
    const card = document.createElement("div");
    card.className = "wardrobe-item-card animate-fade-in";
    card.dataset.category = item.category?.toLowerCase() || "unknown";
    card.dataset.itemId = item.id || item._id;
    
    // Determine image source
    let imageSrc = "https://via.placeholder.com/300x300/e0e0e0/666666?text=No+Image";
    if (item.image_base64) {
        imageSrc = `data:image/jpeg;base64,${item.image_base64}`;
    } else if (item.image_url) {
        imageSrc = item.image_url;
    } else if (item.image_path) {
        const filename = item.image_path.split('/').pop();
        imageSrc = `${CONFIG.API_BASE_URL}/uploads/${filename}`;
    }
    
    const categoryIcon = getCategoryIcon(item.category);
    const colorStyle = item.color ? `background-color: ${item.color.toLowerCase()};` : '';
    
    card.innerHTML = `
        <div class="item-image-container">
            <img src="${imageSrc}" 
                 alt="${item.description || 'Clothing item'}" 
                 class="item-image"
                 loading="lazy" />
            <div class="item-category-badge">
                <i class="fas fa-${categoryIcon}"></i>
                <span>${item.category || 'Unknown'}</span>
            </div>
            ${item.color && item.color !== 'unknown' ? `
                <div class="item-color-indicator" style="${colorStyle}" title="Color: ${item.color}"></div>
            ` : ''}
        </div>
        <div class="item-details">
            <h4 class="item-title" title="${item.description || 'No description'}">
                ${truncateText(item.description || 'No description', 30)}
            </h4>
            
            <div class="item-properties">
                ${item.color && item.color !== 'unknown' ? `
                    <div class="item-property">
                        <i class="fas fa-palette"></i>
                        <span>${item.color}</span>
                    </div>
                ` : ''}
                
                ${item.formality && item.formality !== 'casual' ? `
                    <div class="item-property">
                        <i class="fas fa-user-tie"></i>
                        <span>${item.formality}</span>
                    </div>
                ` : ''}
                
                ${item.season && item.season !== 'all-season' ? `
                    <div class="item-property">
                        <i class="fas fa-sun"></i>
                        <span>${item.season}</span>
                    </div>
                ` : ''}
            </div>
            
            ${item.style_tags && item.style_tags.length > 0 ? `
                <div class="item-tags">
                    ${item.style_tags.slice(0, 3).map(tag => `
                        <span class="item-tag" title="${tag}">${truncateText(tag, 10)}</span>
                    `).join('')}
                    ${item.style_tags.length > 3 ? `<span class="item-tag-more">+${item.style_tags.length - 3}</span>` : ''}
                </div>
            ` : ''}
            
            <div class="item-actions">
                <button class="btn small btn-outline" onclick="useAsFocusItem('${item.id || item._id}')" title="Use as focus item">
                    <i class="fas fa-star"></i> Focus
                </button>
                <button class="btn small btn-secondary" onclick="viewItemDetails('${item.id || item._id}')" title="View details">
                    <i class="fas fa-eye"></i> View
                </button>
            </div>
        </div>
    `;
    
    return card;
}

function updateWardrobeStats(data) {
    if (!elements.wardrobeStats) return;
    
    const totalItems = data.count || 0;
    const categories = [...new Set(data.items.map(item => item.category).filter(Boolean))];
    const categoryCount = categories.length;
    
    elements.wardrobeStats.textContent = `${totalItems} items • ${categoryCount} categories`;
}

function handleCategoryFilterClick(e) {
    if (!e.target.classList.contains("filter-btn")) return;
    
    // Update active button
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.remove("active");
    });
    e.target.classList.add("active");
    
    // Update state and filter items
    STATE.currentCategory = e.target.dataset.category;
    filterWardrobeItems(STATE.currentCategory);
}

function filterWardrobeItems(category) {
    const items = document.querySelectorAll(".wardrobe-item-card");
    
    items.forEach(item => {
        if (category === "all" || item.dataset.category === category) {
            item.style.display = "flex";
        } else {
            item.style.display = "none";
        }
    });
}

function updateCategoryFilter(items) {
    if (!elements.categoryFilter) return;
    
    // Get unique categories from items
    const categories = [...new Set(items.map(item => item.category).filter(Boolean))];
    
    // Keep existing buttons, add missing ones
    const existingButtons = Array.from(elements.categoryFilter.querySelectorAll(".filter-btn"))
        .map(btn => btn.dataset.category);
    
    categories.forEach(category => {
        if (!existingButtons.includes(category)) {
            const button = document.createElement("button");
            button.className = "filter-btn";
            button.dataset.category = category;
            button.innerHTML = `
                <i class="fas fa-${getCategoryIcon(category)}"></i>
                <span>${category}</span>
            `;
            elements.categoryFilter.appendChild(button);
        }
    });
}

function populateFocusItems(items) {
    if (!elements.focusItemSelect) {
        console.error("❌ Focus item select element not found!");
        return;
    }
    
    // Clear existing options except the first one
    elements.focusItemSelect.innerHTML = '<option value="">None (Generate random outfits)</option>';
    
    // Add items
    items.forEach(item => {
        const option = document.createElement("option");
        option.value = item.id || item._id;
        option.textContent = `${item.category || 'Item'}: ${truncateText(item.description || 'No description', 40)}`;
        elements.focusItemSelect.appendChild(option);
    });
    
    console.log(`✅ Populated ${items.length} focus items`);
}

// ==============================
// OUTFIT GENERATION
// ==============================
async function handleGenerateOutfits(e) {
    e.preventDefault();
    
    console.log("🎯 DEBUG: Starting handleGenerateOutfits");
    
    // Get form values - ALL VALUES MUST BE EXTRACTED HERE
    const occasion = elements.occasionSelect?.value?.trim() || "casual day";
    const city = elements.cityInput?.value?.trim() || "";
    const focusItemId = elements.focusItemSelect?.value || null;
    const numOutfits = elements.numOutfitsSlider?.value || 3;
    
    console.log("🔍 Form values:", {
        occasion: occasion,
        city: city,
        focusItemId: focusItemId,
        numOutfits: numOutfits
    });
    
    if (!city) {
        showNotification("Please enter a city", "error");
        elements.cityInput?.focus();
        return;
    }
    
    // Check if user has items
    if (STATE.wardrobeItems.length === 0) {
        showNotification("Please upload some clothing items first!", "warning");
        return;
    }
    
    console.log(`📊 User has ${STATE.wardrobeItems.length} items`);
    
    showLoading("Generating Outfits", `Creating outfits for ${occasion} in ${city}...`);
    
    try {
        console.log("📤 Sending request to backend...");
        const response = await fetch(`${CONFIG.API_BASE_URL}/generate`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                occasion: occasion,
                city: city,
                focus_item_id: focusItemId,
                outfitCount: parseInt(numOutfits),
                user_id: CONFIG.DEFAULT_USER_ID
            })
        });

        console.log("📥 Response status:", response.status);
        
        const responseText = await response.text();
        console.log("📥 Raw response:", responseText);
        
        let data;
        try {
            data = JSON.parse(responseText);
            console.log("📥 Parsed response:", data);
        } catch (parseError) {
            console.error("❌ Failed to parse JSON:", parseError);
            showNotification("Invalid response from server", "error");
            return;
        }
        
        if (data.status === "success") {
            STATE.currentOutfits = data.outfits;
            displayOutfits(data.outfits, data.weather, data.weather_recommendations);
            showNotification(`🎉 Generated ${data.outfits.length} outfits!`, "success");
        } else {
            console.error("❌ Backend error:", data.error);
            showNotification(data.error || "Failed to generate outfits", "error");
        }
        
    } catch (error) {
        console.error("🚨 Fetch error:", error);
        showNotification("Failed to generate outfits: " + error.message, "error");
    } finally {
        hideLoading();
    }
}

function displayOutfits(outfits, weather, recommendations) {
    // Hide placeholder
    if (elements.resultsPlaceholder) {
        elements.resultsPlaceholder.style.display = "none";
    }
    
    // Clear previous results
    if (elements.outfitsGrid) {
        elements.outfitsGrid.innerHTML = "";
    }
    
    // Display weather info
    if (weather && elements.weatherDisplay) {
        displayWeatherInfo(weather, recommendations);
        elements.weatherDisplay.style.display = "block";
    }
    
    // Display each outfit
    outfits.forEach((outfit, index) => {
        const outfitCard = createOutfitCard(outfit, index);
        if (elements.outfitsGrid) {
            elements.outfitsGrid.appendChild(outfitCard);
        }
    });
    
    // Show save button if we have outfits
    if (elements.saveAllOutfitsBtn && outfits.length > 0) {
        elements.saveAllOutfitsBtn.style.display = "inline-block";
    }
    
    // Scroll to results smoothly
    setTimeout(() => {
        const resultsSection = document.getElementById("result");
        if (resultsSection) {
            resultsSection.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'start' 
            });
        }
    }, 100);
}

function createOutfitCard(outfit, index) {
    const card = document.createElement("div");
    card.className = "outfit-card animate-slide-in";
    card.style.animationDelay = `${index * 0.1}s`;
    
    // Create items HTML - WITHOUT COLOR DISPLAY
    let itemsHTML = '';
    if (outfit.items && outfit.items.length > 0) {
        itemsHTML = outfit.items.map(item => {
            // First try to find the exact item from wardrobe
            let originalItem = null;
            let displayName = 'Unknown Item';
            let displayCategory = item.category || 'Item';
            
            // Try multiple ways to match the item:
            // 1. By item_id if provided
            if (item.item_id && STATE.wardrobeItems.length > 0) {
                originalItem = STATE.wardrobeItems.find(w => 
                    w.id === item.item_id || 
                    w._id === item.item_id
                );
            }
            
            // 2. By matching category (removed color matching)
            if (!originalItem && STATE.wardrobeItems.length > 0 && item.category) {
                const categoryItems = STATE.wardrobeItems.filter(w => 
                    w.category && item.category &&
                    w.category.toLowerCase() === item.category.toLowerCase()
                );
                if (categoryItems.length > 0) {
                    originalItem = categoryItems[0]; // Take first match
                }
            }
            
            // If we found the original item, use its real name
            if (originalItem) {
                displayName = originalItem.description || 
                             originalItem.name || 
                             `My ${originalItem.category || 'item'}`;
                displayCategory = originalItem.category || displayCategory;
            } 
            // If not found but item has description from AI
            else if (item.description && item.description !== 'unknown') {
                displayName = item.description;
            }
            // Last resort: create a descriptive name
            else {
                displayName = displayCategory;
            }
            
            // Clean up the display name
            displayName = displayName.charAt(0).toUpperCase() + displayName.slice(1);
            
            // Get style tags from original item if available
            let styleTags = [];
            if (originalItem && originalItem.style_tags) {
                styleTags = originalItem.style_tags;
            } else if (item.style_tags) {
                styleTags = item.style_tags;
            }
            
            // SIMPLIFIED HTML - NO COLOR DISPLAY
            return `
                <div class="outfit-item">
                    <div class="item-icon">
                        <i class="fas fa-${getCategoryIcon(displayCategory)}"></i>
                    </div>
                    <div class="item-info">
                        <h4 class="item-name" title="${displayName}">
                            ${truncateText(displayName, 30)}
                        </h4>
                        <div class="item-meta">
                            <span class="item-category-badge">${displayCategory}</span>
                        </div>
                        ${styleTags.length > 0 
                            ? `<div class="item-style-tags">
                                ${styleTags.slice(0, 2).map(tag => 
                                    `<span class="style-tag">${truncateText(tag, 15)}</span>`
                                ).join('')}
                               </div>`
                            : ''
                        }
                    </div>
                </div>
            `;
        }).join('');
    } else {
        itemsHTML = '<div class="no-items-message">No items specified</div>';
    }
    
    // Rest of the function remains the same...
    // Create styling tips if available
    let stylingTipsHTML = '';
    if (outfit.styling_tips && outfit.styling_tips.length > 0) {
        stylingTipsHTML = `
            <div class="styling-tips">
                <h5><i class="fas fa-lightbulb"></i> Styling Tips</h5>
                <ul>
                    ${outfit.styling_tips.map(tip => `<li>${tip}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    // Create weather adaptation badge
    let weatherBadgeHTML = '';
    if (outfit.weather_adaptation && outfit.weather_adaptation > 0.7) {
        weatherBadgeHTML = `
            <span class="weather-badge" title="Excellent weather adaptation">
                <i class="fas fa-sun"></i> Weather Ready
            </span>
        `;
    }
    
    card.innerHTML = `
        <div class="outfit-header">
            <div class="outfit-title-section">
                <h3 class="outfit-title">${outfit.title || `Outfit ${index + 1}`}</h3>
                ${weatherBadgeHTML}
            </div>
            <p class="outfit-description">${outfit.details || outfit.description || 'Stylish combination'}</p>
        </div>
        
        <div class="outfit-content">
            <div class="outfit-items-section">
                <h4><i class="fas fa-tshirt"></i> Items in this Outfit</h4>
                <div class="outfit-items">
                    ${itemsHTML}
                </div>
            </div>
            
            ${stylingTipsHTML}
            
            <div class="outfit-metrics">
                <div class="metric">
                    <div class="metric-label">Overall Score</div>
                    <div class="metric-value">
                        <div class="score-bar">
                            <div class="score-fill" style="width: ${(outfit.score || 0) * 100}%"></div>
                            <span class="score-text">${((outfit.score || 0) * 10).toFixed(1)}/10</span>
                        </div>
                    </div>
                </div>
                
                ${outfit.weather_adaptation ? `
                <div class="metric">
                    <div class="metric-label">Weather Fit</div>
                    <div class="metric-value">
                        <div class="score-bar">
                            <div class="score-fill" style="width: ${outfit.weather_adaptation * 100}%"></div>
                            <span class="score-text">${(outfit.weather_adaptation * 10).toFixed(1)}/10</span>
                        </div>
                    </div>
                </div>
                ` : ''}
            </div>
        </div>
        
        <div class="outfit-actions">
            <button class="btn btn-primary" onclick="saveOutfit(${index})">
                <i class="fas fa-save"></i> Save to Favorites
            </button>
            <button class="btn btn-outline" onclick="regenerateSimilar(${index})">
                <i class="fas fa-redo"></i> Regenerate Similar
            </button>
        </div>
    `;
    
    return card;
}

async function updateWeatherPreview(city) {
    if (!elements.weatherPreview) return;
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/weather/${city}`);
        const data = await response.json();
        
        if (data.status === "success") {
            elements.weatherPreview.innerHTML = `
                <div class="weather-preview-card">
                    <div class="weather-icon">
                        <i class="fas fa-${getWeatherIcon(data.weather.condition)} fa-2x"></i>
                    </div>
                    <div class="weather-details">
                        <h4>${city}</h4>
                        <div class="weather-temp">${data.weather.temp_c || data.weather.temp || 'N/A'}°C</div>
                        <div class="weather-condition">${data.weather.condition || 'Clear'}</div>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        // Silently fail - preview is optional
    }
}

function displayWeatherInfo(weather, recommendations) {
    if (!elements.weatherDisplay) return;
    
    let recommendationsHTML = '';
    if (recommendations && Object.keys(recommendations).length > 0) {
        recommendationsHTML = `
            <div class="recommendations-section">
                <h5><i class="fas fa-umbrella"></i> Recommendations</h5>
                ${recommendations.layers && recommendations.layers.length > 0 ? `
                    <div class="recommendation-group">
                        <strong>Layers:</strong>
                        <div class="recommendation-tags">
                            ${recommendations.layers.map(layer => `<span class="recommendation-tag">${layer}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${recommendations.colors && recommendations.colors.length > 0 ? `
                    <div class="recommendation-group">
                        <strong>Colors:</strong>
                        <div class="recommendation-tags">
                            ${recommendations.colors.map(color => `<span class="recommendation-tag" style="background-color: ${color === 'dark' ? '#333' : color === 'light' ? '#fff' : color}; color: ${color === 'light' ? '#333' : '#fff'}">${color}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${recommendations.materials && recommendations.materials.length > 0 ? `
                    <div class="recommendation-group">
                        <strong>Materials:</strong>
                        <div class="recommendation-tags">
                            ${recommendations.materials.map(material => `<span class="recommendation-tag">${material}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
    
    elements.weatherDisplay.innerHTML = `
        <div class="weather-info-card">
            <div class="weather-header">
                <h4><i class="fas fa-cloud-sun"></i> Weather in ${weather.city}</h4>
                <div class="weather-refresh" onclick="refreshWeather('${weather.city}')" title="Refresh weather">
                    <i class="fas fa-sync-alt"></i>
                </div>
            </div>
            
            <div class="weather-main">
                <div class="weather-temp-large">${weather.temp_c || weather.temp || 'N/A'}°C</div>
                <div class="weather-condition-large">${weather.condition || 'Clear'}</div>
                <div class="weather-description">${weather.description || ''}</div>
            </div>
            
            ${recommendationsHTML}
            
            <div class="weather-footer">
                <div class="weather-source">
                    <i class="fas fa-database"></i>
                    <span>Source: ${weather.source || 'Weather Service'}</span>
                </div>
                <div class="weather-time">
                    <i class="fas fa-clock"></i>
                    <span>Updated: ${new Date().toLocaleTimeString()}</span>
                </div>
            </div>
        </div>
    `;
}

// ==============================
// HELPER FUNCTIONS
// ==============================
function getCategoryIcon(category) {
    if (!category) return 'tag';
    
    const icons = {
        'top': 'tshirt',
        'bottom': 'jeans',
        'shoes': 'shoe-prints',
        'dress': 'female',
        'jacket': 'vest',
        'sweater': 'hoodie',
        'skirt': 'female',
        'shorts': 'walking',
        'accessory': 'gem',
        'hat': 'hat-cowboy',
        'bag': 'shopping-bag',
        'pants': 'jeans',
        'shirt': 'tshirt'
    };
    
    const categoryLower = category.toLowerCase();
    for (const [key, icon] of Object.entries(icons)) {
        if (categoryLower.includes(key)) {
            return icon;
        }
    }
    
    return 'tag';
}

function getWeatherIcon(condition) {
    if (!condition) return 'sun';
    
    condition = condition.toLowerCase();
    if (condition.includes('rain')) return 'cloud-rain';
    if (condition.includes('snow')) return 'snowflake';
    if (condition.includes('storm')) return 'poo-storm';
    if (condition.includes('cloud')) return 'cloud';
    if (condition.includes('clear') || condition.includes('sun')) return 'sun';
    if (condition.includes('fog') || condition.includes('mist')) return 'smog';
    return 'cloud-sun';
}

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function showLoading(title, message) {
    if (!elements.loadingModal) return;
    
    document.getElementById("loading-title").textContent = title;
    document.getElementById("loading-message").textContent = message;
    elements.loadingModal.style.display = "flex";
    document.body.style.overflow = "hidden";
}

function hideLoading() {
    if (elements.loadingModal) {
        elements.loadingModal.style.display = "none";
        document.body.style.overflow = "auto";
    }
}

function showNotification(message, type = "info") {
    // Remove existing notifications of same type
    const existingNotifications = document.querySelectorAll(`.notification-${type}`);
    existingNotifications.forEach(notification => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    });
    
    // Create notification element
    const notification = document.createElement("div");
    notification.className = `notification notification-${type} animate-slide-in`;
    
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    
    notification.innerHTML = `
        <div class="notification-icon">
            <i class="fas fa-${icons[type] || 'info-circle'}"></i>
        </div>
        <div class="notification-content">
            <div class="notification-message">${message}</div>
        </div>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }
    }, 5000);
}

// ==============================
// GLOBAL FUNCTIONS
// ==============================
window.useAsFocusItem = function(itemId) {
    if (elements.focusItemSelect) {
        elements.focusItemSelect.value = itemId;
        showNotification("Item set as focus for outfit generation", "success");
        
        // Scroll to generate section
        document.getElementById("generate").scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }
};

window.viewItemDetails = async function(itemId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/wardrobe/${itemId}`);
        const data = await response.json();
        
        if (data.status === "success") {
            // Create modal with item details
            const modal = document.createElement("div");
            modal.className = "item-detail-modal";
            modal.innerHTML = `
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>Item Details</h3>
                        <button class="modal-close" onclick="this.parentElement.parentElement.remove()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        <div class="detail-image">
                            <img src="${data.item.image_base64 ? `data:image/jpeg;base64,${data.item.image_base64}` : 'https://via.placeholder.com/400x400'}" 
                                 alt="${data.item.description}" />
                        </div>
                        <div class="detail-info">
                            <h4>${data.item.description}</h4>
                            <div class="detail-properties">
                                <div class="detail-property">
                                    <strong>Category:</strong> ${data.item.category || 'Unknown'}
                                </div>
                                <div class="detail-property">
                                    <strong>Formality:</strong> ${data.item.formality || 'Casual'}
                                </div>
                                <div class="detail-property">
                                    <strong>Season:</strong> ${data.item.season || 'All-season'}
                                </div>
                            </div>
                            ${data.item.style_tags && data.item.style_tags.length > 0 ? `
                                <div class="detail-tags">
                                    <strong>Style Tags:</strong>
                                    <div class="tags-container">
                                        ${data.item.style_tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
        }
    } catch (error) {
        console.error("Failed to load item details:", error);
        showNotification("Failed to load item details", "error");
    }
};

window.saveOutfit = function(index) {
    if (STATE.currentOutfits[index]) {
        showNotification("Outfit saved to your favorites!", "success");
        // In a real app, you would save this to the backend
    }
};

window.regenerateSimilar = function(index) {
    showNotification("Regenerating similar outfits...", "info");
    // Implement regeneration logic here
};

window.refreshWeather = async function(city) {
    if (!city) return;
    
    showNotification("Refreshing weather data...", "info");
    await updateWeatherPreview(city);
    
    // If we're in the results section, update the weather display
    if (elements.weatherDisplay && elements.weatherDisplay.style.display !== "none") {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/weather/${city}`);
            const data = await response.json();
            
            if (data.status === "success") {
                displayWeatherInfo(data.weather, data.recommendations);
                showNotification("Weather data updated", "success");
            }
        } catch (error) {
            showNotification("Failed to refresh weather", "error");
        }
    }
};

async function saveAllOutfits() {
    if (!STATE.currentOutfits || STATE.currentOutfits.length === 0) {
        showNotification("No outfits to save", "warning");
        return;
    }
    
    showLoading("Saving Outfits", "Saving all outfits to your history...");
    
    try {
        // In a real app, you would make an API call here
        await new Promise(resolve => setTimeout(resolve, 1500)); // Simulate API call
        
        showNotification(`Saved ${STATE.currentOutfits.length} outfits to your history!`, "success");
    } catch (error) {
        showNotification("Failed to save outfits", "error");
    } finally {
        hideLoading();
    }
}