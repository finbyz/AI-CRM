// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Trending Topic Generator', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            // Change button text to "Fetch Trending Content"
            frm.add_custom_button(__('Fetch Trending Content'), function() {
                
                // Show initial alert
                frappe.show_alert({
                    message: __('🚀 Fetching trending content...'),
                    indicator: 'blue'
                }, 3);
                
                // // Create progress toast
                // let $toast = $(`
                //     <div id="trending-progress-toast" style="
                //         position: fixed;
                //         bottom: 30px;
                //         right: 30px;
                //         background: white;
                //         padding: 20px 25px;
                //         border-radius: 10px;
                //         box-shadow: 0 5px 25px rgba(0,0,0,0.15);
                //         z-index: 10000;
                //         min-width: 380px;
                //         border-left: 4px solid #2196F3;
                //     ">
                //         <div style="display: flex; align-items: center; margin-bottom: 12px;">
                //             <span id="toast-emoji" style="font-size: 24px; margin-right: 12px;">🚀</span>
                //             <div style="flex: 1;">
                //                 <div style="font-weight: 600; font-size: 14px; color: #2e3338;">
                //                     Fetching Trending Content
                //                 </div>
                //                 <div id="toast-message" style="font-size: 12px; color: #6c757d; margin-top: 4px;">
                //                     Initializing...
                //                 </div>
                //             </div>
                //         </div>
                //         <div class="progress" style="height: 6px; border-radius: 3px; background: #e9ecef;">
                //             <div id="toast-progress-bar" 
                //                 class="progress-bar progress-bar-striped progress-bar-animated" 
                //                 style="
                //                     width: 0%; 
                //                     background: linear-gradient(90deg, #2196F3, #00BCD4);
                //                     transition: width 0.3s ease;
                //                 ">
                //             </div>
                //         </div>
                //         <div id="toast-details" style="
                //             margin-top: 10px;
                //             font-size: 11px;
                //             color: #95a5a6;
                //             max-height: 80px;
                //             overflow-y: auto;
                //         "></div>
                //     </div>
                // `);
                
                // $('body').append($toast);
                
                // // Subscribe to real-time progress updates
                // frappe.realtime.on('trending_topic_progress', function(data) {
                //     if (data.docname === frm.doc.name) {
                //         // Update main message
                //         $('#toast-message').text(data.message);
                        
                //         // Add to details log
                //         if (data.message.includes('✓') || data.message.includes('⚠️')) {
                //             $('#toast-details').prepend(`<div>${data.message}</div>`);
                //         }
                        
                //         // Update progress bar
                //         if (data.percent !== null && data.percent !== undefined) {
                //             $('#toast-progress-bar').css('width', data.percent + '%');
                //         }
                        
                //         // Update emoji based on progress
                //         if (data.percent >= 100) {
                //             $('#toast-emoji').text('🎉');
                //             $('#toast-progress-bar').removeClass('progress-bar-animated');
                //         } else if (data.percent >= 90) {
                //             $('#toast-emoji').text('💾');
                //         } else if (data.percent >= 50) {
                //             $('#toast-emoji').text('📰');
                //         } else if (data.percent >= 20) {
                //             $('#toast-emoji').text('📱');
                //         }
                //     }
                // });
                
                // Make API call to fetch content (NO AI involved)
                frm.call({
                    method: 'fetch_trending_content',  // Changed method name
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            // Success - wait to show completion
                            setTimeout(function() {
                                $('#trending-progress-toast').fadeOut(300, function() {
                                    $(this).remove();
                                });
                                
                                frappe.show_alert({
                                    message: __('✅ Fetched {0} trending items!', 
                                        [r.message.items_fetched]),
                                    indicator: 'green'
                                }, 5);
                                
                                // Reload to show new data
                                frm.reload_doc();
                            }, 1500);
                        }
                    },
                    error: function(r) {
                        $('#trending-progress-toast').remove();
                        
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('Failed to fetch trending content. Check error log.')
                        });
                    }
                });
            }).addClass('btn-primary');
        }
    },
    
    onload: function(frm) {
        // Clean up any leftover toast
        $('#trending-progress-toast').remove();
    }
});