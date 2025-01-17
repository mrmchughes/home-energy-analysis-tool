import React from 'react';
import './button.css';

interface ButtonProps {
  /**
   * Is this the principal call to action on the page?
   */
  primary?: boolean;
  /**
   * What background color to use
   */
  backgroundColor?: string;
  /**
   * How large should the button be?
   */
  size?: 'default' | 'wide' | 'sm' | 'lg' | 'pill' | 'icon';
  /**
   * Button contents
   */
  label: string;
  /**
   * Optional click handler
   */
  variant: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
  onClick?: () => void;
}

/**
 * Primary UI component for user interaction
 */
export const Button = ({
  size = 'default',
  variant,
  backgroundColor,
  label,
  ...props
}: ButtonProps) => {
  
  return (
    <button
      type="button"
      className={['storybook-button', `storybook-button--${variant}`].join(' ')}
      style={{ backgroundColor }}
      {...props}
    >
      {label}
    </button>
  );
};
