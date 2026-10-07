{
    'name': 'Chatter Position',
    'version': '20.0.1.0.1',
    'category': 'Productivity/Discuss',
    'summary': 'Each user chooses whether the chatter sits beside or below forms',
    'description': """
Adds a Chatter Position preference (My Preferences):

- Automatic: standard Odoo, beside the form on very wide screens, below otherwise.
- Below the form: always below, so wide forms and lists inside them get the full width.
- Beside the form: beside the form from large screens up (not only very wide ones).
    """,
    'author': 'Basic Solution Co., Ltd.',
    'website': 'https://www.basic-solution.com',
    'depends': ['mail', 'web_tour'],
    'data': [
        'views/res_users_views.xml',
    ],
    'assets': {
        'web_tour.helpers': [
            ('replace',
             'web_tour/static/src/tour_helpers/tour_helpers_clipboard.js',
             'bs_web_chatter_position/static/compat/tour_helpers_clipboard.js'),
        ],
        'web.assets_backend': [
            'bs_web_chatter_position/static/src/**/*',
        ],
        'web.assets_tests': [
            'bs_web_chatter_position/static/tests/tours/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
