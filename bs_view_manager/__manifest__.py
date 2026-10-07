{
    'name': 'View Manager',
    'version': '20.0.1.3.0',
    'category': 'Hidden/Tools',
    'summary': 'Per-user list layouts: show, hide, reorder, rename and resize columns',
    'depends': ['web'],
    'data': [
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            # templates right after the web one, so that primary copies of
            # web.ListRenderer (sale, account, stock, ...) get these extensions too
            ('after', 'web/static/src/views/list/list_renderer.xml', 'bs_view_manager/static/src/columns_panel/list_renderer_patch.xml'),
            ('after', 'web/static/src/views/list/list_renderer.xml', 'bs_view_manager/static/src/filter_row/filter_row.xml'),
            ('after', 'web/static/src/views/list/list_renderer.xml', 'bs_view_manager/static/src/aggregates/aggregates.xml'),
            'bs_view_manager/static/src/columns_panel/columns_panel.js',
            'bs_view_manager/static/src/columns_panel/columns_panel.xml',
            'bs_view_manager/static/src/columns_panel/columns_panel.scss',
            'bs_view_manager/static/src/columns_panel/list_renderer_patch.js',
            'bs_view_manager/static/src/filter_row/filter_domain.js',
            'bs_view_manager/static/src/filter_row/column_filter.js',
            'bs_view_manager/static/src/filter_row/column_filter.xml',
            'bs_view_manager/static/src/filter_row/filter_row_patch.js',
            'bs_view_manager/static/src/filter_row/filter_row.scss',
            'bs_view_manager/static/src/row_numbers/row_numbers_patch.js',
            'bs_view_manager/static/src/row_numbers/row_numbers.scss',
            'bs_view_manager/static/src/inline_edit/inline_edit_patch.js',
            'bs_view_manager/static/src/inline_edit/inline_edit.scss',
            'bs_view_manager/static/src/aggregates/aggregates_patch.js',
            'bs_view_manager/static/src/aggregates/aggregates.scss',
        ],
    },
    'author': 'Basic Solution Co., Ltd.',
    'website': 'https://www.basic-solution.com',
    'license': 'LGPL-3',
}
